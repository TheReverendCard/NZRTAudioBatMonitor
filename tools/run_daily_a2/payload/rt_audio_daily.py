"""Prepare receipt-validated Shed RT audio without copying or changing WAVs."""
import hashlib,json,os,re,uuid,wave
from collections import defaultdict
from pathlib import Path
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import annotation_care as care
NZ=ZoneInfo('Pacific/Auckland')
def prepare(root):
    import numpy as np
    from PIL import Image
    from avianz_adapter import make_image
    cfg=care.read_json(root/'bat_config.json',{});receiver=cfg.get('receiver',{})
    base=Path(receiver.get('backup_root') or root/'WiFi_Backup')
    if not base.is_absolute():base=root/base
    base=base/'RT_Clips'
    device=str(care.read_json(root/'BatDailyTool/config.json',{}).get('shed_rt_device_id','bcd3d73f1fb8')).lower()
    folder=base/device
    results=defaultdict(list);errors=[];n=0
    for wav in sorted(folder.glob('*/*.wav')):
        try:
            m=json.loads(wav.with_suffix('.json').read_text(encoding='utf-8-sig'))
            if not (m['schema']=='nzrt-mlp-clip-1' and m['source_device']=='Xiao RT' and str(m['device_id']).lower()==device and m['capture_valid'] is True):raise ValueError('unverified/device mismatch')
            local=datetime.fromtimestamp(m['utc_start'],timezone.utc).astimezone(NZ)
            day=(local.date()-timedelta(days=int(local.hour<12))).strftime('%Y%m%d')
            session=str(m['session']);run=int(m['run']);seq=int(m['seq'])
            if not re.fullmatch('[0-9a-fA-F]{8}',session) or min(run,seq)<0 or wav.stem!=local.strftime('%Y%m%d_%H%M%S')+f'_RT_{session}_{run}_{seq}':raise ValueError('identity mismatch')
            with wave.open(str(wav),'rb') as w:
                count=w.getnframes()
                if (w.getframerate(),w.getnchannels(),w.getsampwidth(),w.getcomptype())!=(192000,1,2,'NONE') or not 1024<=count<=384000 or (m['samples'],m['sample_rate'])!=(count,192000):raise ValueError('invalid RT format')
                pcm=w.readframes(count)
            if len(pcm)!=2*count or hashlib.sha256(pcm).hexdigest()!=m['pcm_sha256']:raise ValueError('incomplete or mismatched PCM')
            dest=root/day/('XiaoRT'+day);dest.mkdir(parents=True,exist_ok=True)
            bmp=dest/(wav.stem+'.bmp');receipt=bmp.with_suffix('.rt.json')
            info=dict(device=device,pcm_sha256=m['pcm_sha256'],rt_event_id=f'{session.upper()}:{run}:{seq}',wav=str(wav.resolve()),utc_start=m['utc_start'],duration=count/192000)
            if bmp.exists() or receipt.exists():
                old=care.read_json(receipt,{})
                if not bmp.is_file() or any(old.get(k)!=v for k,v in info.items()) or care.digest(bmp)!=old.get('bmp_sha256'):raise ValueError('existing product conflict')
            else:
                pixels,_=make_image(np.frombuffer(pcm,dtype='<i2'),192000)
                tmp=dest/(uuid.uuid4().hex+'.tmp')
                try:
                    Image.fromarray(pixels).save(tmp,format='BMP');os.link(tmp,bmp)
                finally:tmp.unlink(missing_ok=True)
                care.write_json(receipt,dict(info,bmp_sha256=care.digest(bmp)));n+=1
            results[day].append(bmp)
        except (ValueError,TypeError,KeyError,OSError,wave.Error,EOFError) as e:errors.append(str(wav)+': '+str(e))
    report=dict(folder=str(folder),found=sum(map(len,results.values()))+len(errors),new_bmps=n,verified=sum(map(len,results.values())),issues=errors)
    care.write_json(root/'Daily_Run_Reports'/'RT_Audio'/'latest.json',report)
    print('RT audio:',report['verified'],'verified;',n,'new BMPs;',len(errors),'issues. Source:',folder)
    return results,errors

def classify_received(root,auto):
    from daily_pipeline import classify
    clips,errors=prepare(root)
    for day,bmps in clips.items():
        report=root/'Daily_Run_Reports'/day
        report.mkdir(parents=True,exist_ok=True)
        try:classify(bmps,root,report,'XiaoRT',auto)
        except Exception as e:errors.append(day+' RT AviaNZ: '+str(e))
    return errors
