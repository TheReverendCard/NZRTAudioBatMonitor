from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent
BASE=json.loads((HERE/'base_hashes.json').read_text(encoding='utf8'))
NEW=('RTLogSpool.h',)
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def one(s,a,b):
 if s.count(a)!=1:raise ValueError('GUARD-3 anchor differs: '+a[:80])
 return s.replace(a,b)
def transform(n,s):
 if digest(s)!=BASE[n]:raise ValueError('Unrecognised GUARD-3 dependency: '+n)
 if (HERE/'replacements'/n).is_file():s=(HERE/'replacements'/n).read_text(encoding='utf8')
 s=s.replace('NZRT-J5-GUARD-3','NZRT-J6-GUARD-4')
 if n=='GuardSignals.h':s=one(s,'std::atomic<bool> audioPressure','std::atomic<bool> flashIdle{false}; // main loop, true only after capture and DSP acknowledge stopped\n std::atomic<bool> audioPressure')
 if n=='WildlifeMic.cpp':
  s=one(s,'std::atomic<bool> captureRunning{false};','std::atomic<bool> captureRunning{false};\nstd::atomic<bool> dspIdle{true};')
  s=one(s,'    if(!running) {vTaskDelay(pdMS_TO_TICKS(25));continue;}','    if(!running) {dspIdle.store(true);vTaskDelay(pdMS_TO_TICKS(25));continue;}\n    dspIdle.store(false);')
  s=one(s,'void printHealthIfDue() {','''void printHealthIfDue() {
  RtWatch::sig().flashIdle.store(started && dayStandby && !captureEnabledRequest && !captureRunning && dspIdle.load());
  WildlifeJournal::service();''')
  s=one(s,'  } else {\n    // Reset the analysis time origin','  } else {\n    RtWatch::sig().flashIdle.store(false);\n    // Reset the analysis time origin')
  s=one(s,'  size_t storageTotal=SPIFFS.totalBytes(),storageUsed=SPIFFS.usedBytes();','  size_t storageTotal=WildlifeJournal::stats().storageTotal,storageUsed=WildlifeJournal::stats().storageUsed; // cached, zero means not sampled this boot')
  s=s.replace('NZRT STORAGE total_bytes=', 'NZRT STORAGE cached=1 total_bytes=')
  s=s.replace('flash_write_failures=%lu','journal_enqueue_failures=%lu').replace('candidate_write_failures=%lu','candidate_enqueue_failures=%lu')
  s=s.replace('NZRT CANDIDATE_SAVED session=%08lX run=%lu seq=%lu', 'NZRT CANDIDATE_QUEUED session=%08lX run=%lu seq=%lu storage=ram durable=0')
  s=s.replace('flash writes occur here\n  // on the main loop, batched every ten seconds to minimise interference.', 'journal transactions queue in RAM here\n  // on the main loop, batched every ten seconds. Idle service owns flash.')
  s=s.replace('No prefix is confirmed until close verifies it.', 'No partial transaction is accepted into the RAM queue.')
  s=s.replace('A failed flush may have persisted a prefix; idempotent session/run/seq.', 'RAM transaction was not accepted; retry the pending records.')
  s=s.replace('flash journal open failed','RAM journal enqueue unavailable').replace('cannot write boot marker to SPIFFS','cannot queue boot marker in RAM')
 if n=='WildlifeML.cpp':
  s=s.replace('fetchHash[0]&&WildlifeMic::daytimeStandby()&&idle()', 'fetchHash[0]&&WildlifeJournal::flashSafe()&&idle()')
  s=one(s,'float* workspace=nullptr;', 'float* hotWorkspace=nullptr;\nfloat* workspace=nullptr;')
  s=one(s,'workspace,features,nullptr,ScoreBudget::check,&budget)', 'workspace,features,nullptr,ScoreBudget::check,&budget,hotWorkspace)')
  s=one(s,'workspace=(float*)heap_caps_malloc(RTFeatures::WORK_FLOATS*4,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);','workspace=(float*)heap_caps_malloc(RTFeatures::WORK_FLOATS*4,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);\n hotWorkspace=(float*)heap_caps_malloc(RTFeatures::HOT_FLOATS*4,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);')
  s=one(s,'if(!ring||!workspace||!model||!clips[0].pcm||!clips[1].pcm)', 'if(!ring||!workspace||!hotWorkspace||!model||!clips[0].pcm||!clips[1].pcm)')
  s=one(s,'free(workspace);workspace=nullptr;','free(workspace);workspace=nullptr;free(hotWorkspace);hotWorkspace=nullptr;')
  s=one(s,' RTModel::builtin(*model);bool recoveryFallback=false;', ' note("NZRT FEATURES version=WAV-SCHEMA-1-Q33 scratch=internal bytes=14336 numeric_schema=unchanged");\n RTModel::builtin(*model);bool recoveryFallback=false;')
  # Give audio acquisition priority without delaying ~every 1ms of CPU work.
  # Tick remains a true RTOS block, so idle/watchdog tasks get scheduled.
  s=one(s,'if(now-b.lastYield>=1000)', 'if(now-b.lastYield>=4000)')
 if n=='WildlifeUpload.h':
  s=s.replace('purpose==Purpose::ML?"NZRT WIFI connecting purpose=ML":"NZRT WIFI_LOG connecting;', 'purpose==Purpose::ML?"NZRT WIFI connecting purpose=ML":purpose==Purpose::Ram?"NZRT WIFI connecting purpose=JOURNAL_RAM":"NZRT WIFI_LOG connecting;')
  s=one(s,'enum class Purpose {Snapshot, Live, ML};','enum class Purpose {Snapshot, Live, Ram, ML};\nstatic bool lastWasRam=false;\nstatic unsigned reportsBeforeML=0;')
  a=s.index('static bool sendLive(uint32_t utc)')
  s=s[:a]+'''static bool sendRam(uint32_t utc) {
  uint8_t* body=nullptr;uint64_t token=0;size_t bytes=WildlifeJournal::prepareUpload(body,token);
  if(!bytes)return true;
  char header[128];int hn=snprintf(header,sizeof(header),"NZRT RAM_SNAPSHOT utc=%lu firmware=NZRT-J6-GUARD-4\\n",(unsigned long)utc);
  body-=hn;memcpy(body,header,hn);bytes+=hn;
  uint32_t hash=2166136261u;for(size_t i=0;i<bytes;++i)hash=(hash^body[i])*16777619u;
  char hex[9],device[13];snprintf(hex,sizeof(hex),"%08lx",(unsigned long)hash);
  snprintf(device,sizeof(device),"%012llx",(unsigned long long)ESP.getEfuseMac());
  WiFiClient client;HTTPClient http;http.setConnectTimeout(2000);http.setTimeout(8000);
  bool ok=false;int code=-1;
  if(http.begin(client,String(NZRT_UPLOAD_URL)+"/rt-log")) {
    http.addHeader("Authorization",String("Bearer ")+NZRT_UPLOAD_TOKEN);
    http.addHeader("Content-Type","application/octet-stream");http.addHeader("X-Name",String(device)+".txt");
    http.addHeader("X-Device",device);http.addHeader("X-FNV1a",hex);
    http.addHeader("X-Snapshot-UTC",String((unsigned long)utc));http.addHeader("X-Firmware","NZRT-J6-GUARD-4");
    code=http.POST(body,bytes);ok=code==200 && http.getString()==String("OK ")+hex;http.end();
  }
  WildlifeJournal::finishUpload(ok,token);
  Serial.printf("NZRT HTTP route=/rt-log source=ram bytes=%u code=%d ack_match=%u\\n",unsigned(bytes),code,unsigned(ok));
  return ok;
}

'''+s[a:]
  s=one(s,'if(purpose==Purpose::Live)finishLive(sendLive(utc));','if(purpose==Purpose::Live)finishLive(sendLive(utc));\n      else if(purpose==Purpose::Ram)finishLive(sendRam(utc));')
  s=one(s,'if(purpose==Purpose::Live)finishLive(false);','if(purpose==Purpose::Live||purpose==Purpose::Ram)finishLive(false);')
  s=one(s,'bool journalDue=standby &&', 'bool journalDue=standby && WildlifeJournal::flashSafe() && !WildlifeJournal::inCooldown() &&')
  s=one(s,'  if(!journalDue&&!liveDue&&!mlDue)return false;', '  bool ramDue=WildlifeJournal::hasPendingUpload() && millis()-lastLiveAttempt>=liveDelay;\n  if(!journalDue&&!liveDue&&!mlDue&&!ramDue)return false;')
  s=one(s,'  purpose=WildlifeML::testUploadDue()?Purpose::ML:(journalDue?Purpose::Snapshot:(liveDue?Purpose::Live:Purpose::ML));', '''  bool ramTurn=ramDue && (!liveDue||!lastWasRam);
  purpose=(WildlifeML::testUploadDue() || (mlDue && reportsBeforeML>=2))?Purpose::ML:(journalDue?Purpose::Snapshot:(ramTurn?Purpose::Ram:(liveDue?Purpose::Live:(ramDue?Purpose::Ram:Purpose::ML))));
  if(purpose==Purpose::ML)reportsBeforeML=0;else if(reportsBeforeML<2)++reportsBeforeML;
  if(purpose==Purpose::Ram)lastWasRam=true;else if(purpose==Purpose::Live)lastWasRam=false;''')
 return s

def emit(dest):
 dest=Path(dest);dest.mkdir(parents=True,exist_ok=True)
 for n in BASE:(dest/n).write_text(transform(n,(HERE/'base'/n).read_text(encoding='utf8')),encoding='utf8')
 for n in NEW:(dest/n).write_bytes((HERE/n).read_bytes())
if __name__=='__main__':
 import sys
 emit(sys.argv[1])
