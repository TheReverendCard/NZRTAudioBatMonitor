"""Run and verify the daily AR4 -> conversion -> AviaNZ -> review workflow."""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import bat_tool as core
from flac_archive import export_day as archive_flac_day
from pipeline_summaries import export_summaries
import rt_logs
import annotation_care as care
import source_cli_control

HERE=Path(__file__).resolve().parent
AUTO=HERE/'automation.json'


def now():return datetime.now(timezone.utc).isoformat()


def run_rt_stage(root,day,skip=False,import_path=None):
    """Shared with Collect XiaoRT Logs.bat; separate from AviaNZ receipts."""
    try:
        if import_path:
            path,meta=rt_logs.import_log(root,import_path)
            return rt_logs.collection_status(root,day,'imported',raw_log=path.relative_to(root).as_posix(),
                                            complete=meta['complete'],sha256=meta['sha256'])
        if skip:
            return rt_logs.read_json(root/'Daily_Run_Reports'/day/'XiaoRT/collection.json',{}) or rt_logs.collection_status(root,day,'skipped',note='RT log import skipped with --skip-rt.')
        # XiaoRT sends files to the Wi-Fi receiver.  Prefer these immutable
        # saved files over prompting the user to reconnect the device by USB.
        return rt_logs.import_recent_wifi_backup(root, day)
    except (OSError,ValueError) as e:
        print('XiaoRT collection needs attention:',e,'The rest of the daily run will continue.',flush=True)
        return rt_logs.collection_status(root,day,'failed',error=str(e))


def refresh_timeline(root,cfg,days,warnings):
    try:
        from daily_timeline import refresh
        refresh(root,cfg,days)
        print('Daily timelines:',root/'Daily_Timeline/index.html',flush=True)
    except Exception as e:
        message='Timeline update needs attention: '+str(e)+'; recorder processing continues.'
        if message not in warnings:warnings.append(message)
        print(message,flush=True)
        return False
    return True


def valid_annotation(path):
    from cumulative_summary import annotation
    try:return annotation(path)[1]
    except (OSError,ValueError,TypeError,KeyError,IndexError):return False


def processed(bmp):return valid_annotation(Path(str(bmp)+'.data'))


def safe_conversion_placeholder(bmp):
    """Only BatDaily's original empty Xiao conversion sidecar is replaceable.

    Never mistake a manually reviewed zero-segment annotation for a placeholder.
    """
    bmp=Path(bmp)
    side=Path(str(bmp)+'.data')
    meta=bmp.with_suffix('.conversion.json')
    wav=bmp.with_suffix('.wav')
    if not (side.is_file() and meta.is_file() and wav.is_file()):
        return False
    try:
        obj=core.read_json(side)
        return (isinstance(obj,list) and len(obj)==1 and isinstance(obj[0],dict)
                and not obj[0].get('Operator') and not obj[0].get('Reviewer')
                and not obj[0].get('BatDailyReview') and not obj[0].get('Segments'))
    except (ValueError, OSError, TypeError):
        return False


def configure():
    print('Select the AviaNZ executable you normally launch. This setup is saved once.')
    try:
        import tkinter as tk
        from tkinter import filedialog
        app=tk.Tk();app.withdraw()
        name=filedialog.askopenfilename(title='Select AviaNZ.exe',filetypes=[('AviaNZ application','*.exe'),('All files','*')])
        app.destroy()
    except Exception:
        name=input('Full path to AviaNZ.exe: ').strip().strip('"')
    if not name:raise ValueError('No AviaNZ executable selected. No recordings processed.')
    exe=Path(name).resolve()
    if not exe.is_file():raise ValueError('AviaNZ executable does not exist')
    cfg={'command':[str(exe)],'recogniser':'NZ Bats','timeout_minutes':120}
    cfg['mode']='auto'
    core.write_json(AUTO,cfg)
    print('Saved AviaNZ setup:',AUTO)
    return cfg


def probe(cfg):
    cmd=cfg.get('command')
    if not isinstance(cmd,list) or not cmd or not all(isinstance(v,str) for v in cmd):raise ValueError('automation.json command must be an argument array')
    try:
        r=subprocess.run(cmd+['--help'],capture_output=True,text=True,errors='replace',timeout=30)
    except subprocess.TimeoutExpired:raise ValueError('AviaNZ did not answer --help within 30 seconds. This executable may not support CLI mode. Close any window it opened; no classification was started.')
    text=r.stdout+'\n'+r.stderr
    if r.returncode or not all(v in text for v in ('--cli','--batchmode','--sdir1','--recogniser')):
        raise ValueError('Installed AviaNZ did not advertise the expected batch CLI options. Check the executable selected with Configure AviaNZ.bat. No classification started.\n'+text[-1500:])


def inputs(root,day):
    day_root=root/day
    if not day_root.is_dir():raise ValueError('Daily recording folder does not exist: '+str(day_root))
    ar4=[];wav=[];has_xiao_dir=False
    for folder in sorted(day_root.iterdir()):
        if not folder.is_dir():continue
        if re.fullmatch(r'ar4\d{8}',folder.name,re.I):ar4.extend(p for p in folder.iterdir() if p.is_file() and p.suffix.lower()=='.bmp')
        if re.fullmatch(r'xiao\d{8}',folder.name,re.I):
            has_xiao_dir=True
            wav.extend(p for p in folder.iterdir() if p.is_file() and p.suffix.lower()=='.wav')
    return sorted(ar4),sorted(wav)


def available_days(root):
    """Return date folders containing recorder files, ignoring pre-created empty folders."""
    days=[]
    for p in root.iterdir():
        if not p.is_dir() or not re.fullmatch(r'\d{8}',p.name):continue
        found=False
        for sub in p.iterdir():
            if not sub.is_dir():continue
            if re.fullmatch(r'xiao\d{8}',sub.name,re.I):
                found=any(f.is_file() and f.suffix.lower()=='.wav' for f in sub.iterdir())
            elif re.fullmatch(r'ar4\d{8}',sub.name,re.I):
                found=any(f.is_file() and f.suffix.lower()=='.bmp' for f in sub.iterdir())
            if found:break
        if found:days.append(p.name)
    return sorted(days)


def create_next_day_folders(root,day):
    """Provision the next collection date and the two expected recorder folders."""
    next_day=(datetime.strptime(day,'%Y%m%d')+timedelta(days=1)).strftime('%Y%m%d')
    created=[]
    for path in (root/next_day,root/next_day/('Xiao'+next_day),root/next_day/('AR4'+next_day)):
        if path.exists() and not path.is_dir():
            raise ValueError('Cannot create next-day data folder because a file already exists: '+str(path))
        if not path.exists():
            path.mkdir()
            created.append(path)
    return next_day,created


def fingerprints(files,root):return {p.relative_to(root).as_posix():core.sha(p) for p in sorted(set(files))}


def configuration_key(cfg,auto):
    # Empty-AR4 handling and notes do not change the processing outputs for a
    # previously complete day, so preserve old receipt keys and avoid replaying
    # every historical day just because this launcher was updated.
    return hashlib.sha256(json.dumps({'scan':cfg,'avianz':auto,'pipeline_version':'1.4'},sort_keys=True).encode()).hexdigest()



def ensure_source_cli(root, auto):
    """Enable the *already validated* isolated CLI instead of launching GUI batch.

    This function never touches the packaged GUI. The source installer verifies
    archived-model identity and creates an automation.json history snapshot.
    A failed preflight leaves automation.json and recordings unchanged.
    """
    if auto.get('mode') == 'source_cli':
        return auto
    if auto.get('mode') not in ('gui', 'auto', None):
        raise ValueError('Unknown AviaNZ automation mode; refusing automatic classification: '+str(auto.get('mode')))
    base=root/'AviaNZ_CLI_Source_Test'
    if not base.is_dir():
        raise ValueError('Automatic AviaNZ CLI not installed at '+str(base)+'. No manual batch was launched. Reinstall the validated CLI or choose explicit recovery; reviews remain unchanged.')
    print('Configuring verified source AviaNZ CLI (original NZ Bats control); original GUI remains unchanged.', flush=True)
    return source_cli_control.setup(base,auto_path=AUTO)


def verify_receipt(root,day,cfg,auto):
    try:receipt=core.read_json(root/'Daily_Run_Reports'/day/'receipt.json',{})
    except (ValueError,OSError):return False,'completion receipt is unreadable; re-verification required'
    if not isinstance(receipt,dict):return False,'invalid completion receipt'
    if receipt.get('status')!='complete':return False,'no verified complete run'
    if receipt.get('configuration_key')!=configuration_key(cfg,auto):return False,'processing settings changed'
    try:
        ar4,wav=inputs(root,day)
        # New, deleted or changed recordings must invalidate the old completion.
        if fingerprints(ar4+wav,root)!=receipt.get('inputs'):return False,'recordings changed since completion'
        for path,digest in receipt.get('outputs',{}).items():
            p=root/path
            if not p.is_file() or core.sha(p)!=digest:return False,'missing or changed output: '+path
        if not receipt.get('outputs'):return False,'completion has no verified outputs'
    except (OSError,ValueError,TypeError,AttributeError) as e:return False,str(e)
    return True,'verified input and output hashes'


class ManualPending(ValueError):
    pass


def manual_classify(pending,auto,stage):
    """Use the installed GUI when its packaged CLI is unavailable."""
    for folder in sorted({p.parent for p in pending}):
        print('\n'+stage+': open AviaNZ Batch Processing, choose NZ Bats, and process:\n'+str(folder),flush=True)
        print('Save the MACHINE BATCH results only, and DO NOT manually review yet.',flush=True)
        print('Return here once AviaNZ finishes so Bat Daily can preserve the first-pass Backup before any edits. Enter q to resume later.',flush=True)
        if not sys.stdin.isatty():
            raise ManualPending('Manual AviaNZ processing required: '+str(folder)+'; then rerun Run Daily Scan.bat. Experimental BMPs are already generated.')
        command=auto.get('gui_command',auto['command'])
        try:subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except OSError as e:print('Could not open AviaNZ automatically:',e,'Open it normally instead.')
        try:reply=input('Press Enter after processing, or q to finish later: ').strip().lower()
        except EOFError:reply='q'
        if reply in ('q','quit','exit'):
            raise ManualPending('Waiting for manual AviaNZ results in '+str(folder))
        missing=[p.name for p in pending if p.parent==folder and not processed(p)]
        if missing:
            raise ManualPending('Still missing valid saved annotations for '+str(len(missing))+' files in '+str(folder)+'. Examples: '+', '.join(missing[:3])+'. Save batch results there and rerun.')
        # Only the files that were pending immediately before this GUI batch are
        # eligible for a current machine-only backup; old reviewed data is not.
        for bmp in (p for p in pending if p.parent==folder):
            result=care.machine_snapshot(bmp,engine=auto.get('recogniser','NZ Bats'),origin='gui_batch_confirmed',batch_id=now())
            if result['status']=='existing_baseline_preserved':
                print('Existing machine backup preserved:',bmp.name,flush=True)
        print('Machine annotations safely backed up for',folder,flush=True)


def remember_gui(auto,reason):
    auto['mode']='gui'
    auto['cli_unavailable_reason']=reason
    # Only update the selected saved configuration, never another installation.
    saved=core.read_json(AUTO,{})
    if saved.get('command')==auto.get('command'):core.write_json(AUTO,auto)
    print(reason+' Using guided AviaNZ GUI processing from now on.',flush=True)


def classify(bmps,root,report,stage,auto):
    pending=[p for p in bmps if not processed(p)]
    print(stage+':',len(bmps)-len(pending),'already processed;',len(pending),'need AviaNZ',flush=True)
    if not pending:return {'total':len(bmps),'reused':len(bmps),'processed':0}
    command=auto.get('command')
    if not isinstance(command,list) or not command or not all(isinstance(x,str) and x for x in command):
        raise ValueError('Configure AviaNZ.bat must select a valid executable command')
    # This release has an explicit non-destructive CLI-only policy. If an
    # existing config is still GUI, abort instead of asking for manual batch.
    if auto.get('mode') != 'source_cli':
        raise ValueError('Automatic AviaNZ CLI is not active. No manual batch or changes to your reviews were attempted. Run Enable Source CLI Control.bat to diagnose configuration.')
    # A partially written or invalid annotation is not an unprocessed file.
    # Never replace a pre-existing sidecar, even inside isolated CLI processing.
    conflicts=[str(p)+'.data' for p in pending if Path(str(p)+'.data').exists() and not safe_conversion_placeholder(p)]
    if conflicts:
        raise ValueError('Existing annotation(s) are invalid or incomplete and must be inspected, NOT overwritten: '+', '.join(conflicts[:4]))
    # Run only new/unprocessed BMPs in an isolated work folder. AviaNZ cannot
    # delete daily summaries or overwrite human-reviewed source annotations.
    job=report/'Work'/(stage+'_'+uuid.uuid4().hex[:10]);job.mkdir(parents=True)
    mapping={}
    for i,src in enumerate(pending):
        target=job/str(i)/src.name;target.parent.mkdir();shutil.copy2(src,target);mapping[target]=src
    log=report/(stage+'_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.log')
    command=auto['command']+['-c','-b','-d',str(job),'-r',auto.get('recogniser','NZ Bats')]
    spawn_options={}
    if auto.get('mode')=='source_cli':
        model=Path(auto.get('control_model_file',''))
        definition=Path(auto.get('control_filter_file',''))
        if not model.is_file() or care.digest(model)!=auto.get('control_model_sha256'):
            raise ValueError('Control NZ Bats MODEL hash mismatch or model missing. Automatic batch blocked. Restore the archived original model before continuing.')
        if not definition.is_file() or care.digest(definition)!=auto.get('control_filter_sha256'):
            raise ValueError('Control NZ Bats FILTER hash mismatch or config missing. Automatic batch blocked.')
        base=Path(auto.get('appdata_dir',''))
        if not (base/'AviaNZ'/'AviaNZconfig.txt').is_file():
            raise ValueError('Isolated source AviaNZ APPDATA configuration missing.')
        environment=os.environ.copy(); environment['APPDATA']=str(base)
        spawn_options={'cwd':auto['cwd'],'env':environment}
    # Two known AviaNZ CLI questions: resume, launch. Fresh jobs have only launch.
    # Blank stdin beyond these replies causes an explicit failure, not a hang.
    with log.open('w',encoding='utf-8') as handle:
        handle.write('Command: '+json.dumps(command)+'\n');handle.flush()
        proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=handle,stderr=subprocess.STDOUT,text=True,**spawn_options)
        try:proc.communicate(input='y\ny\n',timeout=float(auto.get('timeout_minutes',120))*60)
        except subprocess.TimeoutExpired:
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True)
            if proc.poll() is None:proc.kill()
            proc.communicate()
            raise ValueError(stage+' timed out. See '+str(log))
    if proc.returncode:
        error=log.read_text(encoding='utf-8',errors='replace')
        if "No module named 'cli'" in error or 'No module named "cli"' in error:
            raise ValueError('Source CLI failed to import its CLI module. GUI fallback was NOT launched. No reviewed files changed; inspect '+str(log))
        raise ValueError(stage+' exited with code '+str(proc.returncode)+'. See '+str(log))
    missing=[p.name for p in mapping if not processed(p)]
    if missing:raise ValueError(stage+' returned without valid processed annotations for '+str(len(missing))+' BMPs. Examples: '+', '.join(missing[:3])+'. See '+str(log))
    for work,src in mapping.items():
        # Do not clobber an annotation written by a concurrent manual AviaNZ run.
        out=Path(str(src)+'.data')
        if processed(src):continue
        # Save the untouched isolated machine prediction FIRST, so even a
        # crash while installing the working annotation cannot lose it.
        result=care.machine_snapshot(src,engine=auto.get('recogniser','NZ Bats'),origin='isolated_cli_batch',batch_id=job.name,source_data=Path(str(work)+'.data'))
        if out.exists():core.copy_original(out,report/'Annotation_Backups'/(core.sha(out)[:16]+'_'+out.name))
        temp=out.with_name(out.name+'.pipeline-tmp');shutil.copy2(Path(str(work)+'.data'),temp);temp.replace(out)
        if result['status']=='existing_baseline_preserved':
            print('Existing machine baseline was preserved:',out.name,flush=True)
    return {'total':len(bmps),'reused':len(bmps)-len(pending),'processed':len(pending),'log':str(log),'backed_up':len(pending)}


def converted(root,day,wav,cfg):
    dc={**cfg,**cfg.get('days',{}).get(day,{})}
    if dc.get('convert')=='none':raise ValueError('Daily automation requires conversion. Set convert to all or events in config.json.')
    selected=[w for w in wav if dc.get('convert','all')=='all' or w.name.lower().startswith('event_')]
    if not selected:raise ValueError('No WAVs selected for experimental conversion')
    result=[]
    for w in selected:
        bmp=w.parent/(w.stem+'.bmp')
        meta=core.read_json(bmp.with_suffix('.conversion.json'),{})
        if not bmp.exists() or meta.get('wav_sha256')!=core.sha(w):raise ValueError('Missing or stale conversion: '+str(bmp))
        result.append(bmp)
    return result


def run_day(root,day,cfg,auto,field_notes=None):
    report=root/'Daily_Run_Reports'/day;report.mkdir(parents=True,exist_ok=True)
    old_receipt=core.read_json(report/'receipt.json',{})
    if field_notes is None:field_notes=old_receipt.get('field_notes','')
    ar4_status='present' if any(re.fullmatch(r'ar4\d{8}',p.name,re.I) for p in (root/day).iterdir() if p.is_dir()) else 'directory_missing'
    xiao_dirs=[p for p in (root/day).iterdir() if p.is_dir() and re.fullmatch(r'xiao\d{8}',p.name,re.I)]
    xiao_status='present' if xiao_dirs else 'directory_missing'
    receipt={'day':day,'status':'running','started_utc':now(),'stages':{},'configuration_key':configuration_key(cfg,auto),'field_notes':str(field_notes or ''),'ar4_input_status':ar4_status,'xiao_input_status':xiao_status}
    # Keep previous completion/failure evidence instead of erasing it.
    prev=report/'receipt.json'
    if prev.exists():core.copy_original(prev,report/'History'/(uuid.uuid4().hex+'.json'))
    core.write_json(prev,receipt)
    try:
        ar4,wav=inputs(root,day);before=fingerprints(ar4+wav,root)
        if not wav:
            receipt['xiao_input_status']='no_xiao_wavs' if xiao_dirs else 'directory_missing'
            receipt.setdefault('warnings',[]).append('No XIAO WAV recordings were available; Xiao conversion, harmonics and FLAC archiving were skipped.')
            core.write_json(prev,receipt)
        if not ar4:
            has_ar4_dir=any(re.fullmatch(r'ar4\d{8}',p.name,re.I) for p in (root/day).iterdir() if p.is_dir())
            receipt['ar4_input_status']='no_ar4_bmps' if has_ar4_dir else 'directory_missing'
            core.write_json(prev,receipt)
        print('Matching and converting',day,flush=True)
        # Import may report a stale/incomplete previous experimental analysis.
        # Verify this day's scan errors separately, then import again after AviaNZ.
        core.scan(root,cfg,day)
        scan_report=core.read_json(root/'Matched/Reports'/(day+'.json'),{})
        scan_issues=scan_report.get('issues',[])
        # Bad individual files are retained in issues.csv and excluded from
        # this run, while valid recordings from either device still proceed.
        if scan_issues:
            receipt.setdefault('warnings',[]).append(str(len(scan_issues))+' file processing issue(s); unreadable files were skipped. See Matched/issues.csv.')
            if not receipt.get('field_notes') and sys.stdin.isatty():
                try:
                    answer=input('Some recordings could not be read and will be skipped. Add a note (for example, "SD Card corruption"); press Enter/type ESC to continue without one: ').strip()
                    if answer.upper()!='ESC' and answer!=chr(27):receipt['field_notes']=answer
                except EOFError:pass
        inventory=scan_report.get('inventory',[])
        valid_ar4=sorted(Path(x['file']) for x in inventory if x.get('kind')=='AR4' and x.get('file'))
        valid_wav=sorted(Path(x['file']) for x in inventory if x.get('kind') in ('event','periodic') and x.get('file'))
        scan_warnings=scan_report.get('warnings',[])
        for warning in scan_warnings:
            message=warning.get('warning','') if isinstance(warning,dict) else str(warning)
            if message and message not in receipt.setdefault('warnings',[]):receipt['warnings'].append(message)
        if not valid_ar4:
            receipt.setdefault('warnings',[]).append('No readable AR4 BMP detections were available; the AR4 summary is empty.')
        if wav and not valid_wav:
            receipt['xiao_input_status']='unreadable_or_skipped'
        if ar4 and not valid_ar4:
            receipt['ar4_input_status']='unreadable_or_skipped'
        exported_sources={str(x.get('source','')) for x in scan_report.get('exports',[])}
        dc={**cfg,**cfg.get('days',{}).get(day,{})}
        conversion_wavs=[w for w in valid_wav if dc.get('convert','all')=='all' or (dc.get('convert')=='events' and w.name.lower().startswith('event_'))]
        successful_conversions=[w for w in conversion_wavs if w.name in exported_sources]
        if len(successful_conversions)<len(conversion_wavs):
            receipt.setdefault('warnings',[]).append(str(len(conversion_wavs)-len(successful_conversions))+' XIAO WAV conversion(s) failed and were skipped; see Matched/issues.csv.')
        bmps=converted(root,day,successful_conversions,cfg) if successful_conversions else []
        receipt['stages']['scan']={'conversions':len(bmps)};core.write_json(prev,receipt)
        receipt['stages']['ar4']=classify(valid_ar4,root,report,'AR4',auto)
        if not valid_ar4:receipt['stages']['ar4']['status']='no_ar4_bmps' if not ar4 else 'no_readable_ar4_bmps'
        core.write_json(prev,receipt)
        export_summaries(valid_ar4,report/'AR4_Summaries')
        receipt['stages']['experimental']=classify(bmps,root,report,'Experimental',auto);core.write_json(prev,receipt)
        export_summaries(bmps,report/'Experimental_Summaries')
        core.experimental_review.sync(root,core)
        # Ensure current positive annotations actually became active review records.
        positives,annotation_errors=core.experimental_review.collect(root/day/('Xiao'+day))
        if annotation_errors:raise ValueError('Experimental result import has '+str(len(annotation_errors))+' annotation/summary error(s); see Experimental_Review/issues.csv')
        records={p.parent.name:core.read_json(p) for p in (root/'Experimental_Review').glob('*/'+day+'/*/record.json')}
        for name in positives:
            stem=name[:-len('.bmp.data')];r=records.get(stem,{})
            if not r.get('active') or r.get('missing_files'):raise ValueError('Incomplete experimental review entry: '+stem)
        if not all(processed(p) for p in valid_ar4+bmps):raise ValueError('Not all readable input BMPs have valid AviaNZ annotations')
        ar4_after,wav_after=inputs(root,day)
        if fingerprints(ar4_after+wav_after,root)!=before:raise ValueError('Recordings changed during this run. Finish copying files and rerun.')
        core.index_archive(root)
        outputs=[Path(str(p)+'.data') for p in valid_ar4+bmps]+bmps
        for folder in sorted({bmp.parent/'Backup' for bmp in valid_ar4+bmps}):
            if folder.is_dir():
                outputs.extend(folder.glob('*.bmp.data'))
                if (folder/'manifest.json').is_file():outputs.append(folder/'manifest.json')
        outputs+=list((report/'AR4_Summaries').glob('*.xlsx'))+list((report/'Experimental_Summaries').glob('*.xlsx'))
        for base in [root/'Matched/Pairs'/day,root/'Matched/Harmonics'/day,root/'Experimental_Review/Additional'/day,root/'Experimental_Review/Already_Matched'/day]:
            if base.exists():outputs.extend(p for p in base.rglob('*') if p.is_file())
        show_backlog(root,"After processing")
        from cumulative_summary import update_summary
        update_summary(root,cfg)
        # Final post-processing stage: retain exact WAV masters, create verified
        # FLAC training copies, and include the archive in this day's receipt.
        if valid_wav:
            flac_result=archive_flac_day(root,day,valid_wav)
            receipt['stages']['flac_archive']={'total':flac_result['total'],'reused':flac_result['reused'],'verified':flac_result['verified'],'manifest':str(flac_result['manifest'])}
            outputs.extend(flac_result['outputs'])
        else:
            receipt['stages']['flac_archive']={'status':'skipped_no_xiao_wavs','total':0,'reused':0,'verified':0}
        ar4_final,wav_final=inputs(root,day)
        if fingerprints(ar4_final+wav_final,root)!=before:raise ValueError('Recordings changed during FLAC export. Finish copying files and rerun.')
        receipt.update(status='complete',finished_utc=now(),inputs=before,outputs=fingerprints(outputs,root),configuration_key=configuration_key(cfg,auto))
        receipt['stages']['import']={'positive_recordings':len(positives)}
        core.write_json(prev,receipt)
        print(day+': COMPLETE and verified',flush=True)
        if valid_wav:print('FLAC training archive:',flac_result['verified'],'verified; originals retained.',flush=True)
        else:print('XIAO-dependent work skipped; available AR4 work and summaries completed.',flush=True)
        if not ar4:print('No AR4 BMPs found; XIAO results, harmonics and summaries were still processed.',flush=True)
        return True
    except Exception as e:
        receipt.update(status='awaiting_manual' if isinstance(e,ManualPending) else 'failed',finished_utc=now(),error=str(e));core.write_json(prev,receipt)
        print(day+(': WAITING FOR AVIANZ: ' if isinstance(e,ManualPending) else ': FAILED: ')+str(e),flush=True)
        return False


def status_page(root,checks,warnings):
    base=root/'Daily_Run_Reports';base.mkdir(parents=True,exist_ok=True)
    rows=[]
    for day,ok,reason in checks:
        receipt=core.read_json(base/day/'receipt.json',{})
        links=[]
        for suffix,title in [('receipt.json','Run details'),('AR4_Summaries/DetectionSummary_Any_sound.xlsx','AR4 summary'),('Experimental_Summaries/DetectionSummary_Any_sound.xlsx','Experimental summary'),('XiaoRT/collection.json','RT collection')]:
            if (base/day/suffix).exists():links.append('<a href="'+day+'/'+suffix+'">'+title+'</a>')
        if (root/'Daily_Timeline'/day/'index.html').exists():links.append('<a href="../Daily_Timeline/'+day+'/index.html">Three-recorder timeline</a>')
        note_parts=[]
        rt=core.read_json(base/day/'XiaoRT/collection.json',{})
        if rt:
            rt_note='XiaoRT: '+rt.get('status','unknown')
            if rt.get('note'):rt_note+=' ('+str(rt['note'])+')'
            if rt.get('error'):rt_note+=' ('+str(rt['error'])+')'
            note_parts.append(rt_note)
        if receipt.get('ar4_input_status') in ('directory_missing','no_ar4_bmps'):
            note_parts.append('No AR4 BMPs recorded ('+str(receipt.get('ar4_input_status'))+')')
        if receipt.get('field_notes'):note_parts.append(str(receipt['field_notes']))
        note_parts.extend(str(x) for x in receipt.get('warnings',[]))
        note=html.escape(' | '.join(note_parts))
        rows.append('<tr><td>'+day+'</td><td>'+('PASS' if ok else 'NEEDS ATTENTION')+'</td><td>'+html.escape(reason)+'</td><td>'+note+'</td><td>'+' | '.join(links)+'</td></tr>')
    page='<!doctype html><meta charset="utf-8"><title>Daily processing status</title><style>body{font:16px system-ui;max-width:1100px;margin:35px auto;padding:15px;background:#f2f6f7;color:#172c33}td,th{padding:12px;text-align:left;border-bottom:1px solid #ccc}a{color:#12687c}</style><h1>Daily processing status</h1><p>Updated '+now()+'</p><p><a href="../Daily_Timeline/index.html">Three-recorder timelines</a> | <a href="../AviaNZ_Summary/AviaNZ_All_Days.xlsx">All-days spreadsheet</a> | <a href="../Matched/index.html">Paired review</a> | <a href="../Experimental_Review/index.html">Experimental positives</a> | <a href="../Training_FLAC/index.html">Training FLAC archive</a></p>'+''.join('<p>'+html.escape(w)+'</p>' for w in warnings)+'<table><tr><th>Recording folder</th><th>Check</th><th>Result</th><th>Field notes</th><th>Reports</th></tr>'+''.join(rows)+'</table><p>PASS verifies files and pipeline completion, not biological classification accuracy. RT collection is optional and reported separately. AviaNZ summaries here are generated by BatDailyTool from saved annotations.</p>'
    (base/'index.html').write_text(page,encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=HERE.parent)
    parser.add_argument('--day',help='Process one YYYYMMDD folder, checking the preceding day first')
    parser.add_argument('--notes',help='Optional field note for the requested/latest day, e.g. SD card corrupted')
    parser.add_argument('--flac-only',action='store_true',help='Export and verify FLAC copies for the requested or latest day without rerunning AviaNZ')
    parser.add_argument('--configure',action='store_true')
    parser.add_argument('--skip-rt',action='store_true',help='Skip the optional USB log prompt; keep previously imported RT records')
    parser.add_argument('--rt-log',type=Path,help='Import a particular XiaoRT serial or receiver log')
    parser.add_argument('--recover-history',action='store_true',help='Explicitly retry incomplete older dates; default processes the latest day ONLY')
    a=parser.parse_args();root=a.root.resolve()
    if not root.is_dir():raise ValueError('Bat root does not exist')
    from run_integrity import run_lock
    with run_lock(root,'daily'):
        return run_locked(a,root)

def show_backlog(root,label):
    try:
        from review_unreviewed_queue import ReviewQueue
        ReviewQueue(root).backlog(label)
    except Exception as exc:
        print(label+': review count unavailable: '+str(exc),flush=True)

def run_locked(a,root):
    if a.configure:configure();return 0
    if not root.is_dir():raise ValueError('Bat root does not exist')
    if a.flac_only:
        days=available_days(root)
        if not days:raise ValueError('No YYYYMMDD daily folders found in '+str(root))
        target=a.day or days[-1]
        if target not in days:raise ValueError('Requested daily folder not found')
        _,wav=inputs(root,target)
        result=archive_flac_day(root,target,wav)
        print('FLAC archive complete:',result['verified'],'files verified; originals retained.')
        print('Archive index:',root/'Training_FLAC'/'index.html')
        return 0
    status_page(root,[],['Starting setup and verification. This run is not yet complete.'])
    cfg={**core.DEFAULTS,**core.read_json(HERE/'config.json',{})}
    days=available_days(root)
    if not days:raise ValueError('No YYYYMMDD daily folders found in '+str(root))
    target=a.day or days[-1]
    if target not in days:raise ValueError('Requested daily folder not found')
    # Provision independently of AviaNZ, RT, reports and processing receipts.
    next_day,_=create_next_day_folders(root,target)
    print('Next collection folders ready:',root/next_day,flush=True)
    print('Review backlog: not yet scanned for this run.',flush=True)
    try:
        from external_inventory import register
        register(root)
    except Exception as e:print('External intake PARTIAL:',e,flush=True)
    # Download even when this day's AviaNZ receipt is already complete, and
    # before a broken AviaNZ installation can prevent the optional retrieval.
    run_rt_stage(root,target,skip=a.skip_rt,import_path=a.rt_log)
    preliminary_warnings=[]
    refresh_timeline(root,cfg,[d for d in days if d<=target],preliminary_warnings)
    try:
        auto=core.read_json(AUTO) or configure()
        # Do this even for a fully processed day, so the next new recordings
        # are handled automatically by the source CLI instead of a GUI prompt.
        auto=ensure_source_cli(root,auto)
    except Exception as e:
        status_page(root,[],preliminary_warnings+['Source CLI setup failed, original recordings unchanged: '+str(e)])
        raise
    try:
        from rt_audio_daily import classify_received
        preliminary_warnings.extend(classify_received(root,auto))
    except Exception as exc:preliminary_warnings.append('RT clip intake PARTIAL: '+str(exc))
    previous=(datetime.strptime(target,'%Y%m%d')-timedelta(days=1)).strftime('%Y%m%d')
    warnings=list(preliminary_warnings)
    gap_warning=previous not in days and any(d<target for d in days)
    if gap_warning:warnings.append('Previous calendar folder '+previous+' is missing. Its run cannot be verified; processing available folders continues.')
    elif previous not in days:warnings.append('First available recording day: no earlier daily folder is present. This run establishes the initial verified baseline.')
    # Default: process only the newest collection folder. Old dates may have
    # hand-reviewed sidecars, even when they lack a completed pipeline receipt.
    # Never retry their machine batches implicitly. Explicit opt-in required.
    selected=([d for d in days if d<=target] if a.recover_history else [target])
    older=[d for d in days if d<target]
    if older and not a.recover_history:
        print('SAFETY: older collection days will NOT be reprocessed automatically ('+str(len(older))+' older days).',flush=True)
        print('Use --recover-history only after reviewing any historical unprocessed files.',flush=True)
    checks=[]
    try:
        for day in selected:
            # Migration must also run for previously completed days.  It moves
            # only exact, WAV-linked legacy BMP bundles and never overwrites a
            # different existing reviewed sidecar.
            migration=care.migrate_xiao(root,day)
            if migration['moved']:
                print(day+': moved',migration['moved'],'legacy Xiao files beside WAV masters.',flush=True)
            for problem in migration['conflicts']+migration['missing_wav']:
                message='Legacy Xiao migration needs manual attention: '+problem
                if message not in warnings:warnings.append(message)
                print(message,flush=True)
            ok,reason=verify_receipt(root,day,cfg,auto)
            print(day+': '+reason,flush=True)
            if not ok:
                try:
                    ar4_files,xiao_files=inputs(root,day)
                    # --help can succeed even when the packaged CLI import is missing.
                    # Classification validates actual results and offers the GUI fallback.
                except Exception as e:
                    checks.append((day,False,str(e)));status_page(root,checks,warnings)
                    print(day+': preflight failed: '+str(e),flush=True)
                    continue
                # Probe before launching any classification. A fully reused run
                # can finish with saved outputs even when no CLI is needed.
                field_notes=None
                if day==target:
                    field_notes=a.notes
                    if field_notes is None and sys.stdin.isatty():
                        missing=[]
                        if not ar4_files:missing.append('AR4 BMP files')
                        if not xiao_files:missing.append('XIAO WAV files')
                        if missing:
                            prompt='Missing/empty '+ ' and '.join(missing)+'. Add a field note (or press Enter/type ESC to continue without one): '
                            try:
                                answer=input(prompt).strip()
                                field_notes=None if answer.upper()=='ESC' or answer=='\x1b' else (answer or None)
                            except EOFError:field_notes=None
                ok=run_day(root,day,cfg,auto,field_notes=field_notes)
                completed=core.read_json(root/'Daily_Run_Reports'/day/'receipt.json',{})
                if ok and not xiao_files:
                    reason='completed; XIAO-dependent stages skipped and available AR4 results processed'
                elif ok and not ar4_files:
                    reason='completed and verified; no AR4 BMPs, XIAO processing continued'
                elif ok and completed.get('warnings'):
                    reason='completed with skipped file(s); see recorded warnings and Matched/issues.csv'
                else:
                    reason='completed and verified' if ok else completed.get('error','failed')
            checks.append((day,ok,reason));status_page(root,checks,warnings)
        show_backlog(root,"After processing")
        from cumulative_summary import update_summary
        update_summary(root,cfg)
        if not refresh_timeline(root,cfg,[d for d in days if d<=target],warnings):
            checks.append((target,False,"PARTIAL: recorder results retained; final timeline refresh failed"))
        return 0 if all(c[1] for c in checks) else 1
    finally:
        show_backlog(root,"End of processing")
        status_page(root,checks,warnings)

if __name__=='__main__':
    try:sys.exit(main())
    except (OSError,ValueError) as e:print('ERROR:',e,file=sys.stderr);sys.exit(1)
