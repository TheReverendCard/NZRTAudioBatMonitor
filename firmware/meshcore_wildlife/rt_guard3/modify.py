from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent
BASE=json.loads((HERE/'base_hashes.json').read_text())
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def one(s,a,b):
 if s.count(a)!=1:raise ValueError('GUARD-2 anchor differs: '+a[:80])
 return s.replace(a,b)
def region(s,a,b,new):
 i=s.index(a);j=s.index(b,i);return s[:i]+new+s[j:]
def transform(n,s):
 if digest(s)!=BASE[n]:raise ValueError('Unknown dependency version: '+n)
 s=s.replace('NZRT-J4-GUARD-2','NZRT-J5-GUARD-3')
 if n=='RTFeatures.h':
  from features_patch import upgrade
  return upgrade(s)
 if n=='WildlifeJournal.h':
  from journal_patch import upgrade
  return upgrade(s)
 if n=='GuardSignals.h':
  s=one(s,'std::atomic<bool> forceLegacy', 'std::atomic<bool> audioPressure{false};\n std::atomic<bool> forceLegacy')
 if n=='WildlifeMic.cpp':
  s=one(s,'    if(queueDrop)queueDepth=poolCapacity;', '    if(queueDrop)queueDepth=poolCapacity;\n    RtWatch::sig().audioPressure.store(RtWatch::pressure(queueDepth,poolCapacity));')
  s=one(s,'WildlifeDetector::guardPressure(RtWatch::pressure(uxQueueMessagesWaiting(dspQueue),poolCapacity));','RtWatch::sig().audioPressure.store(RtWatch::pressure(uxQueueMessagesWaiting(dspQueue),poolCapacity));\n    WildlifeDetector::guardPressure(RtWatch::sig().audioPressure.load());')
  s=one(s,'return liveCount!=0 || liveHealth[0];','return liveCount!=0 || liveHealth[0] || WildlifeJournal::diagnosticDue();')
  s=one(s,'  size_t used=strlen(liveHealth),count=0;\n  memcpy(buf,liveHealth,used+1);','''  size_t count=0;
  if(capacity<1024){if(capacity)buf[0]=0;return 0;}
  WildlifeJournal::ramStatus(buf,capacity,sessionId);
  size_t used=strlen(buf);buf[used++]='\\n';buf[used]=0;
  size_t healthSize=strlen(liveHealth);
  if(used+healthSize<capacity){memcpy(buf+used,liveHealth,healthSize+1);used+=healthSize;}''')
  s=one(s,'  liveHealth[0]=0;','  liveHealth[0]=0;WildlifeJournal::diagnosticAck();')
 if n=='WildlifeML.cpp':
  s=one(s,'#include "GuardSignals.h"','#include "GuardSignals.h"\n#include "RTClipLease.h"')
  s=one(s,'FREE,FILLING,READY,SCORING,RESULT,UPLOAD','FREE,FILLING,READY,SCORING,RESULT,UPLOAD,OWNED')
  s=one(s,'struct Clip {','''struct Clip {
 RTClipLease lease;
 bool loadProbe=false;
 const char* scoreReason="pending";
 uint32_t featureUs=0,modelUs=0,waitUs=0,chunkUs=0;''')
  s=one(s,'Clip clips[2];','''std::atomic<bool> inferenceEnabled{true},loadRequest{false};
 std::atomic<uint32_t> scoreSkipped{0},scoreValid{0},loadBusy{0};
 bool loadActive=false,loadRunning=false,savedInference=true,savedWav=false,savedActive=false;
 bool loadInject=false; // DSP-owned only
 uint32_t loadEnd=0,loadNext=0;
 std::atomic<uint32_t> loadSeq{0x80000000UL};
 char loadPhase[16]="none";
 void loadStop();
 Clip clips[2];''')
  s=region(s,'void worker(void*) {','bool loadFile(', (HERE/'score_worker.inc').read_text())
  s=one(s,'bool passCommand(const String& cmd){',(HERE/'load_controls.inc').read_text()+'\nbool passCommand(const String& cmd){')
  s=one(s,'bool ok=last==id && !cmd.startsWith("pass ");','bool ok=last==id && !cmd.startsWith("pass ") && cmd!="health status";')
  s=one(s,'if(cmd.startsWith("pass "))ok=passCommand(cmd);','if(cmd.startsWith("infer ") || cmd=="health status")ok=workCommand(cmd);\n  else if(loadActive)ok=false;\n  else if(cmd.startsWith("pass "))ok=passCommand(cmd);')
  s=one(s,'  int result=http.POST(id);','  char health[512];controlStatus(health,sizeof(health));http.addHeader("X-NZRT-Work",health);\n  WildlifeJournal::ramStatus(health,sizeof(health),session);http.addHeader("X-NZRT-Journal",health);\n  int result=http.POST(id);')
  s=one(s,'bool diagnostic=&c==&scan;','bool diagnostic=&c==&scan || c.loadProbe;')
  s=one(s,'http.addHeader("X-Test-Source",scanSource);','http.addHeader("X-Test-Source",c.loadProbe?"load_probe":scanSource);')
  s=one(s,'String((unsigned long)missingSamples)','String((unsigned long)(c.loadProbe?0:missingSamples))')
  s=one(s,'wavEnabled=p.getBool("wav",false);','inferenceEnabled=p.getBool("infer",true);wavEnabled=p.getBool("wav",false);')
  s=one(s,' if(stagedN==CHUNK)flushPcm();',''' if(stagedN==CHUNK){flushPcm();
  if(loadRequest.exchange(false)){
   loadInject=true;trigger(0,++loadSeq,millis());loadInject=false;
   if(!requestedClipSeq)++loadBusy;
  }
 }''')
  # requestedClipSeq is declared after pcm(), use its existing public accessor.
  s=s.replace('if(!requestedClipSeq)++loadBusy;','if(!clipOwnerSeq())++loadBusy;')
  s=one(s,' if (wavEnabled.load() && !benchRaw.load()) {',' if (!loadInject && wavEnabled.load() && !benchRaw.load()) {')
  s=one(s,'  c.passCfg=WildlifeDetector::passCurrent();','  c.loadProbe=loadInject;\n  c.passCfg=WildlifeDetector::passCurrent();')
  s=one(s,'namespace WildlifeML { namespace {','namespace WildlifeML { uint32_t clipOwnerSeq(); namespace {')
  s=one(s,' if(bench && int32_t(now-benchEnd)>=0){',' if(loadActive && int32_t(now-loadEnd)>=0)loadStop();\n if(bench && int32_t(now-benchEnd)>=0){')
  s=region(s,'void tick(){','void status(Print& out)',(HERE/'clip_tick.inc').read_text())
  s=one(s,'void status(Print& out){','void status(Print& out){char work[512];controlStatus(work,sizeof(work));out.println(work);')
  s=one(s,' if(!strncmp(line,"nzrt pass ",10))',' if(!strncmp(line,"nzrt load ",10))return loadCommand(line+10);\n if(!strncmp(line,"nzrt infer ",11) || !strcmp(line,"nzrt health status"))return workCommand(String(line+5));\n if(loadActive && (!strncmp(line,"nzrt pass ",10)||!strncmp(line,"nzrt wav ",9)||!strncmp(line,"nzrt ml ",8)||!strncmp(line,"nzrt model ",11)||!strncmp(line,"nzrt test ",10)||!strncmp(line,"nzrt compare ",13)||!strncmp(line,"nzrt scan ",10)||!strcmp(line,"nzrt record now")) && strcmp(line,"nzrt ml status") && strcmp(line,"nzrt test status")){note("NZRT LOAD command_deferred=1");return true;}\n if(!strncmp(line,"nzrt pass ",10))')
  # Test initialization never reuses a stale probe marker.
  s=s.replace('c.test=true;', 'c.loadProbe=false;c.test=true;')
  s=one(s,' for(auto& c:clips)if(c.state.load()==UPLOAD&&!wavEnabled.load())c.state.store(FREE);','')
  s=s.replace('c.state.load()==UPLOAD','c.state.load()==OWNED && c.lease.delivery')
  s=one(s,'if(ok||c.attempts>=3||!wavEnabled.load())c.state.store(FREE);','if(ok||c.attempts>=3||!wavEnabled.load())c.lease.delivery=false;')
  s=one(s,'note(line);c.state.store(FREE);}else clipsWaiting=true;', 'note(line);c.lease.delivery=false;}else clipsWaiting=true;')
  s=one(s,'"NZRT WAV session=%08lx run=%lu seq=%lu result=%s attempt=%u",(unsigned long)session','"NZRT %s session=%08lx run=%lu seq=%lu result=%s attempt=%u",c.loadProbe?"LOAD_WAV":"WAV",(unsigned long)session')
  s=s.replace('"NZRT WAV session=%08lx run=%lu seq=%lu result=DISCARDED reason=connection_retries",(unsigned long)session','"NZRT %s session=%08lx run=%lu seq=%lu result=DISCARDED reason=connection_retries",c.loadProbe?"LOAD_WAV":"WAV",(unsigned long)session')
 return s

def emit(dest):
 dest=Path(dest);dest.mkdir(parents=True,exist_ok=True)
 for n in BASE:(dest/n).write_text(transform(n,(HERE/'base'/n).read_text()))
 for n in ['RTClipLease.h','RTJournalPolicy.h','RTFeatureControl.h']:(dest/n).write_bytes((HERE/n).read_bytes())
if __name__=='__main__':
 import sys
 emit(sys.argv[1])
