#include "WildlifeML.h"
#include "WildlifeMic.h"
#include "WildlifeDetector.h"
#include "WildlifeTime.h"
#include "WildlifeJournal.h"
#include "WildlifeUploadConfig.h"
#include "RTFeatures.h"
#include "RTOverlapReference.h"
#include "RTModel.h"
#include <Preferences.h>
#include <SPIFFS.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <esp_heap_caps.h>
#include <esp_timer.h>
#include <mbedtls/sha256.h>
#include <atomic>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#include "WildlifeDay.h"
namespace WildlifeDay { void benchWake(uint32_t seconds); }
namespace WildlifeMic {void compareCounters(bool start,const char* stage);}
namespace WildlifeTime {bool compareNetworkIdle();}
namespace WildlifeML { namespace {
constexpr size_t PRE=48000, TOTAL=384000;
enum State:uint8_t { FREE,FILLING,READY,SCORING,RESULT,UPLOAD };
struct Clip {
 std::atomic<uint8_t> state{FREE};int16_t* pcm=nullptr;size_t n=0;
 uint32_t run=0,seq=0,start=0,trigger=0,us=0,queued=0;uint8_t attempts=0;
 unsigned passCfg=8;
 bool rawBench=false,captureComplete=false,valid=false,active=false,wav=false,test=false;float probability=NAN;float threshold=0;
};
// One independent diagnostic buffer. Only the DSP writes PCM, and the main
// loop owns HTTP, command handling and retries. State publishes buffer ownership.
enum ScanState : uint8_t { Empty, Armed, Sampling, Captured };
std::atomic<ScanState> scanState{Empty};
Clip scan;
uint32_t scanId=0, missingSamples=0, scanDue=0, requestTime=0, nextScanAttempt=0;
uint32_t benchEnd=0, period=0, lastSampleBlock=0;
bool bench=false, announced=false;
enum CompareStage : unsigned { Normal, Capture, Score, Send };
std::atomic<unsigned> stage{Normal};
std::atomic<bool> preparing{false};
uint32_t stageStart=0, baseline=0, diagnosticSeq=0;
bool issued=false;
const char* stageName(unsigned s){return s==Capture?"capture":s==Score?"score":s==Send?"send":"normal";}
std::atomic<bool> benchRaw{false};
const char* scanSource="manual";
Clip clips[2];int16_t* ring=nullptr;size_t ringAt=0,ringN=0;
float* workspace=nullptr;RTModel::Model* model=nullptr;TaskHandle_t task=nullptr;
std::atomic<bool> enabled{false},activeMode{false},wavEnabled{false};
std::atomic<uint32_t> skipped{0},gaps{0},completed{0};
uint32_t session=0,nextNet=0,acked=0,failed=0,networkFailures=0,nextControl=10000;char modelHash[65]="builtin-wav-mlp-v01";char fetchHash[65]={};
int modelSlot=-1;
portMUX_TYPE modelGate=portMUX_INITIALIZER_UNLOCKED;bool mutating=false;
void yieldWorker(){vTaskDelay(1);}
void hashBytes(const uint8_t* p,size_t n,char hex[65]) {uint8_t h[32];mbedtls_sha256_ret(p,n,h,0);for(int i=0;i<32;++i)sprintf(hex+2*i,"%02x",h[i]);hex[64]=0;}
bool idle(){for(auto& c:clips)if(c.state.load()!=FREE)return false;return true;}
struct Mutation {
 bool ok;
 Mutation(){portENTER_CRITICAL(&modelGate);ok=!mutating&&idle();if(ok)mutating=true;portEXIT_CRITICAL(&modelGate);}
 ~Mutation(){if(ok){portENTER_CRITICAL(&modelGate);mutating=false;portEXIT_CRITICAL(&modelGate);}}
};
void note(const char* text){Serial.println(text);WildlifeJournal::Writer f;if(f){f.println(text);f.close();}}
// Inside the WildlifeML namespace. Only the ML worker uses these timers.
uint32_t overlapWaitUs = 0;
void overlapYield() {
 const int64_t begin = esp_timer_get_time();
 yieldWorker();
 overlapWaitUs += uint32_t(esp_timer_get_time() - begin);
}

void runOverlapTrial(Clip& clip, float* current) {
 float reference[165];
 static bool cachedFirst = false;
 bool referenceOK = false, cachedOK = false;
 uint32_t elapsed[2] = {}, waits[2] = {};
 for (int pass = 0; pass < 2; ++pass) {
  const unsigned cached = cachedFirst ? (1 - pass) : pass;
  overlapWaitUs = 0;
  const int64_t begin = esp_timer_get_time();
  if (cached) cachedOK = RTFeatures::compute(clip.pcm, clip.n, workspace, current, overlapYield);
  else referenceOK = ReferenceFeatures::compute(clip.pcm, clip.n, workspace, reference, overlapYield);
  elapsed[cached] = uint32_t(esp_timer_get_time() - begin);
  waits[cached] = overlapWaitUs;
 }
 const bool same = referenceOK && cachedOK && memcmp(reference,current,sizeof(reference)) == 0;
 Serial.printf("NZRT OVERLAP result=%s order=%s old_us=%lu cached_us=%lu old_wait_us=%lu cached_wait_us=%lu samples=%lu\n",
   same ? "MATCH" : "FAIL", cachedFirst ? "cached_first" : "old_first",
   (unsigned long)elapsed[0], (unsigned long)elapsed[1], (unsigned long)waits[0],
   (unsigned long)waits[1], (unsigned long)clip.n);
 cachedFirst = !cachedFirst;
}

void worker(void*) {
 for(;;){bool worked=false;for(auto& c:clips){uint8_t expected=READY;
  if(!c.state.compare_exchange_strong(expected,SCORING))continue;worked=true;
  int64_t start=esp_timer_get_time();float features[165];c.probability=NAN;
  c.captureComplete=c.valid && c.n==TOTAL;
  if(c.test && c.seq==UINT32_MAX){
   runOverlapTrial(c,features);c.test=false;c.state.store(FREE);continue;
  }
  if(c.rawBench){
   c.us=0;c.state.store(RESULT);++completed;continue;
  }
  if(c.captureComplete && RTFeatures::compute(c.pcm,c.n,workspace,features,yieldWorker)){
   if(c.test){for(int i=0;i<164;++i)if(fabsf(features[i])>1e-5f)c.valid=false;
    if(fabsf(features[164]-log1pf(float(RTFeatures::MAX_FRAMES)))>1e-5f)c.valid=false;}
   c.probability=RTModel::score(*model,features);
  }
  c.valid=c.valid&&std::isfinite(c.probability);c.threshold=model->threshold;c.us=uint32_t(esp_timer_get_time()-start);
  c.state.store(RESULT);++completed;}
  vTaskDelay(pdMS_TO_TICKS(worked?1:20));
 }
}
bool loadFile(const char* path,const char* expected,RTModel::Model& dest) {
 File f=SPIFFS.open(path,FILE_READ);if(!f||f.size()!=RTModel::BYTES)return false;
 uint8_t* data=(uint8_t*)heap_caps_malloc(RTModel::BYTES,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);if(!data)return false;
 bool ok=f.read(data,RTModel::BYTES)==RTModel::BYTES;f.close();char hash[65];hashBytes(data,RTModel::BYTES,hash);
 ok=ok&&strcmp(hash,expected)==0&&RTModel::decode(data,RTModel::BYTES,dest);free(data);return ok;
}
bool saveBool(const char* key,bool value){Preferences p;if(!p.begin("nzrt-ml",false))return false;bool ok=p.putBool(key,value)>0;p.end();return ok;}
bool fetchModel() {
 // No concurrent model reader; held clips must be processed/discarded first.
 if(!WildlifeMic::daytimeStandby())return false;
 Mutation mutation;if(!mutation.ok)return false;
 WiFiClient client;HTTPClient http;http.setConnectTimeout(2000);http.setTimeout(5000);
 if(!http.begin(client,String(NZRT_UPLOAD_URL)+"/rt-model/"+fetchHash))return false;
 http.addHeader("Authorization",String("Bearer ")+NZRT_UPLOAD_TOKEN);
 int code=http.GET();if(code!=200||http.getSize()!=int(RTModel::BYTES)){http.end();return false;}
 if(SPIFFS.totalBytes()-SPIFFS.usedBytes()<393216UL+RTModel::BYTES){http.end();return false;}
 int slot=modelSlot==0?1:0;String path=String("/rt_model")+slot+".bin";
 File f=SPIFFS.open(path,FILE_WRITE);if(!f){http.end();return false;}
 int written=http.writeToStream(&f);f.flush();f.close();http.end();
 auto* candidate=(RTModel::Model*)heap_caps_malloc(sizeof(RTModel::Model),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
 bool ok=candidate&&written==int(RTModel::BYTES)&&loadFile(path.c_str(),fetchHash,*candidate);
 if(ok){Preferences p;ok=p.begin("nzrt-ml",false);if(ok){
   // Selection is a single NVS string containing slot and hash. Old model remains rollback.
   String selection=String(slot)+":"+fetchHash;ok=p.putString("selection",selection)>0;p.end();}
  if(ok){*model=*candidate;strcpy(modelHash,fetchHash);modelSlot=slot;activeMode=false;note("NZRT MODEL updated mode=shadow");}}
 free(candidate);if(!ok)SPIFFS.remove(path);return ok;
}
uint32_t pollInterval() {
 return bench || period || millis()<600000UL ? 10000UL : 1800000UL;
}
const char* lastScanEvent="NONE";
void reportScan(const char* event) {
 lastScanEvent=event;
 char line[240];
 snprintf(line,sizeof(line),"NZRT TEST session=%08lx run=0 seq=%lu source=%s result=%s",
     (unsigned long)session,(unsigned long)scanId,scanSource,event);
 note(line);
}
bool requestScan(bool scheduled) {
 if(!scan.pcm){note("NZRT TEST rejected=no_diagnostic_buffer");return false;}
 if(scanState.load()!=Empty){note("NZRT TEST rejected=previous_clip_pending");return false;}
 if(!bench) WildlifeDay::testWake();
 scanSource=scheduled?"periodic":"manual";++scanId;
 scan.seq=scanId;scan.run=0;scan.n=0;scan.attempts=0;missingSamples=0;
 requestTime=millis();nextScanAttempt=requestTime;announced=false;
 scanState.store(Armed);reportScan("ARMED");return true;
}
bool testCommand(const char* cmd) {
 if(stage.load()!=Normal){note("NZRT TEST rejected=comparison_active");return false;}
 if(!strcmp(cmd,"record now"))return requestScan(false);
 if(!strcmp(cmd,"test on")){
   bench=true;benchRaw.store(true);benchEnd=millis()+3600000UL;
   WildlifeDay::benchWake(3600);nextNet=nextControl=millis();
   note("NZRT TEST bench=ON duration_s=3600");return true;
 }
 if(!strcmp(cmd,"test off")){
   bench=false;benchRaw.store(false);period=0;WildlifeDay::autoMode();note("NZRT TEST bench=OFF periodic=OFF");return true;
 }
 if(!strcmp(cmd,"scan off")){period=0;note("NZRT TEST periodic=OFF");return true;}
 if(!strncmp(cmd,"scan every ",11)){
   char* end=nullptr;long seconds=strtol(cmd+11,&end,10);
   if(*end || seconds<10 || seconds>86400){note("NZRT TEST invalid_interval range_s=10..86400");return false;}
   period=uint32_t(seconds)*1000;scanDue=millis();note("NZRT TEST periodic=ON");return true;
 }
 return false;
}

bool passCommand(const String& cmd){
 char msg[320];
 if(cmd=="pass status"){WildlifeDetector::passStatus(msg,sizeof(msg));note(msg);return true;}
 for(unsigned a=0;a<3;++a)for(unsigned s=0;s<4;++s){
   if(s==a+1)continue;
   if(cmd!=String("pass ")+WildlifeDetector::passName(a)+" "+(s?WildlifeDetector::passName(s-1):"off"))continue;
   unsigned cfg=a+4*s;
   if(!WildlifeDetector::preparePass(cfg)){note("NZRT FIRST_PASS error=resource");return false;}
   Preferences p;if(!p.begin("nzrt-ml",false))return false;
   bool saved=p.getUInt("pass1",255)==cfg || p.putUInt("pass1",cfg)>0;p.end();
   if(saved)WildlifeDetector::requestPass(cfg);
   WildlifeDetector::passStatus(msg,sizeof(msg));note(msg);
   return saved && WildlifeDetector::passApplied(cfg);
 }
 note("NZRT FIRST_PASS invalid_selection");return false;
}

void pollControl() {
 nextControl=millis()+pollInterval();
 char device[13];snprintf(device,sizeof(device),"%012llx",(unsigned long long)ESP.getEfuseMac());
 WiFiClient client;HTTPClient http;http.setConnectTimeout(2000);http.setTimeout(3000);
 if(!http.begin(client,String(NZRT_UPLOAD_URL)+"/rt-control/"+device))return;
 http.addHeader("Authorization",String("Bearer ")+NZRT_UPLOAD_TOKEN);
 int code=http.GET();
 if(code!=200||http.getSize()<34||http.getSize()>220){http.end();if(code!=204){char line[96];snprintf(line,sizeof(line),"NZRT CONTROL poll_http=%d check_receiver=1",code);note(line);}return;}
 String body=http.getString();http.end();int sep=body.indexOf('\n');if(sep!=32)return;
 String id=body.substring(0,32),cmd=body.substring(33);cmd.trim();
 for(int i=0;i<32;++i)if(!((id[i]>='0'&&id[i]<='9')||(id[i]>='a'&&id[i]<='f')))return;
 Preferences p;String last="";if(p.begin("nzrt-ml",true)){last=p.getString("control","");p.end();}
 bool ok=last==id && !cmd.startsWith("pass ");
 if(!ok){
  if(cmd.startsWith("pass "))ok=passCommand(cmd);
  else if(cmd=="record now" || cmd=="test on" || cmd=="test off" || cmd=="scan off" || cmd.startsWith("scan every ")){ok=testCommand(cmd.c_str());}
  else if(cmd=="wav on"||cmd=="wav off"){
   bool on=cmd=="wav on";ok=saveBool("wav",on);if(ok)wavEnabled=on;
  } else if(cmd=="mode shadow"||cmd.startsWith("mode active ")) {
   bool active=cmd.startsWith("mode active ");
   if(!active||(enabled.load()&&cmd.substring(12)==modelHash)){
    ok=p.begin("nzrt-ml",false);if(ok){ok=p.putString("promoted",active?modelHash:"")>0;p.end();}if(ok)activeMode=active;
   }
  } else if(cmd.startsWith("model fetch ")){
   String h=cmd.substring(12);bool valid=h.length()==64;
   for(int i=0;valid&&i<64;++i)valid=(h[i]>='0'&&h[i]<='9')||(h[i]>='a'&&h[i]<='f');
   if(valid&&enabled.load()){
    ok=p.begin("nzrt-ml",false);if(ok){ok=p.putString("fetch",h)>0;p.end();}if(ok)strcpy(fetchHash,h.c_str());
   }
  }
  if(ok && last!=id){bool saved=p.begin("nzrt-ml",false);if(saved){saved=p.putString("control",id)>0;p.end();}ok=saved;}
 }
 if(!ok){note("NZRT CONTROL rejected_or_deferred=1");return;}
 if(http.begin(client,String(NZRT_UPLOAD_URL)+"/rt-control-ack/"+device)){
  http.addHeader("Authorization",String("Bearer ")+NZRT_UPLOAD_TOKEN);http.addHeader("Content-Type","text/plain");
  if(cmd.startsWith("pass ")){char msg[320];WildlifeDetector::passStatus(msg,sizeof(msg));http.addHeader("X-NZRT-Pass",msg);}
  int result=http.POST(id);http.end();note(result==200?"NZRT CONTROL accepted ack=OK":"NZRT CONTROL accepted ack=RETRY");
 }
}
bool upload(Clip& c) {
 // PCM16 at 192kHz; dedicated route prevents the SD receiver's 96kHz wrapping.
 uint32_t h=2166136261u;const uint8_t* bytes=(const uint8_t*)c.pcm;size_t n=c.n*2;
 for(size_t i=0;i<n;++i)h=(h^bytes[i])*16777619u;
 char hash[9],device[13],name[128],stamp[32];snprintf(hash,sizeof(hash),"%08lx",(unsigned long)h);
 snprintf(device,sizeof(device),"%012llx",(unsigned long long)ESP.getEfuseMac());
 uint32_t utc=WildlifeTime::epochForUptime(c.start);
 // Header UTC remains authoritative. Receiver constructs NZ local display filename.
 snprintf(name,sizeof(name),"%lu_%08lx_%lu_%lu.wav",(unsigned long)utc,(unsigned long)session,(unsigned long)c.run,(unsigned long)c.seq);
 snprintf(stamp,sizeof(stamp),"%llu",(unsigned long long)utc*1000000ULL);
 WiFiClient client;HTTPClient http;http.setConnectTimeout(2000);http.setTimeout(8000);
 bool diagnostic=&c==&scan;
 const char* route=diagnostic?"/rt-test-clip":"/rt-clip";
 if(!http.begin(client,String(NZRT_UPLOAD_URL)+route)){Serial.printf("NZRT HTTP route=%s stage=begin failed=1\n",route);return false;}
 if(diagnostic){
   http.addHeader("X-Test-Source",scanSource);
   http.addHeader("X-Missing-Samples",String((unsigned long)missingSamples));
 }
 http.addHeader("Authorization",String("Bearer ")+NZRT_UPLOAD_TOKEN);http.addHeader("Content-Type","application/octet-stream");
 http.addHeader("X-Name",name);http.addHeader("X-Device",device);http.addHeader("X-FNV1a",hash);
 http.addHeader("X-Sample-Rate","192000");http.addHeader("X-Start-UTC-Us",stamp);http.addHeader("X-Capture-Valid",c.captureComplete?"1":"0");
 if(!diagnostic)http.addHeader("X-First-Pass",WildlifeDetector::passName(c.passCfg&3));
 if(c.rawBench)http.addHeader("X-Test-Source","bench_candidate");
 http.addHeader("X-Firmware","NZRT-J4-PASS-1");http.addHeader("X-Model",modelHash);
 int code=http.POST((uint8_t*)bytes,n);bool ok=code==200&&http.getString()==String("OK ")+hash;
 Serial.printf("NZRT HTTP route=%s seq=%lu code=%d ack_match=%d\n",route,(unsigned long)c.seq,code,ok);
 http.end();return ok;
}
}
bool passCaptureBusy(){for(auto& c:clips)if(c.state.load()==FILLING)return true;return scanState.load()==Sampling;}
bool begin(uint32_t id) {
 {Preferences p;if(p.begin("nzrt-ml",true)){unsigned cfg=p.getUInt("pass1",8);p.end();WildlifeDetector::requestPass(cfg);}}
 session=id;
 // Audio model operation requires PSRAM; original detector continues if unavailable.
 ring=(int16_t*)heap_caps_malloc(PRE*2,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
 workspace=(float*)heap_caps_malloc(RTFeatures::WORK_FLOATS*4,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
 model=(RTModel::Model*)heap_caps_malloc(sizeof(RTModel::Model),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
 for(auto& c:clips)c.pcm=(int16_t*)heap_caps_malloc(TOTAL*2,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
 if(!ring||!workspace||!model||!clips[0].pcm||!clips[1].pcm){
  free(ring);ring=nullptr;free(workspace);workspace=nullptr;free(model);model=nullptr;for(auto& c:clips){free(c.pcm);c.pcm=nullptr;}
  note("NZRT ML unavailable reason=PSRAM original_detector=ON");return false;}
 RTModel::builtin(*model);bool recoveryFallback=false;Preferences p;
 if(p.begin("nzrt-ml",true)){
  wavEnabled=p.getBool("wav",false);String selection=p.getString("selection","");
  if(selection.length()==66&&(selection[0]=='0'||selection[0]=='1')&&selection[1]==':'){
   int slot=selection[0]-'0';String path=String("/rt_model")+slot+".bin";
   if(loadFile(path.c_str(),selection.c_str()+2,*model)){modelSlot=slot;strcpy(modelHash,selection.c_str()+2);}
   else {RTModel::builtin(*model);recoveryFallback=true;note("NZRT MODEL fallback=builtin invalid_saved_model=1");}}
  activeMode=!recoveryFallback&&p.getString("promoted","")==modelHash;
  String pending=p.getString("fetch","");if(pending.length()==64 && pending!=modelHash)strcpy(fetchHash,pending.c_str());p.end();}
 if(xTaskCreatePinnedToCore(worker,"rt_mlp",8192,nullptr,1,&task,0)!=pdPASS){note("NZRT ML unavailable reason=TASK original_detector=ON");return false;}
 scan.pcm=(int16_t*)heap_caps_malloc(TOTAL*sizeof(int16_t),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
 enabled=true;status();return true;
}
// The DSP worker owns this staging area. Flush at trigger and gap boundaries.
constexpr size_t CHUNK=128;
static int16_t staged[CHUNK];
static size_t stagedN=0;
static std::atomic<uint32_t> shortHistory{0};
static void flushPcm() {
 if(!stagedN)return;
 const size_t first=std::min(stagedN,PRE-ringAt);
 memcpy(ring+ringAt,staged,first*sizeof(int16_t));
 memcpy(ring,staged+first,(stagedN-first)*sizeof(int16_t));
 ringAt+=stagedN;
 if(ringAt>=PRE)ringAt-=PRE;
 ringN=std::min(PRE,ringN+stagedN);
 for(auto& c:clips)if(c.state.load()==FILLING){
   size_t count=std::min(TOTAL-c.n,stagedN);
   memcpy(c.pcm+c.n,staged,count*sizeof(int16_t));
   c.n+=count;
   if(c.n==TOTAL)c.state.store(READY);
 }
 stagedN=0;
}
void pcm(float sample) {
 if(!enabled.load(std::memory_order_relaxed))return;
 float v=std::max(-1.f,std::min(32767.f/32768.f,sample));
 staged[stagedN++]=int16_t(lrintf(v*32768.f));
 if(stagedN==CHUNK)flushPcm();
}
const char* triggerReason="unavailable"; // DSP-owned; copied into event at onset
// Written and sampled by the detector task at each candidate onset.
uint32_t requestedClipSeq = 0;
uint32_t clipOwnerSeq() { return requestedClipSeq; }
unsigned compareStage(){return stage.load();}
const char* clipRequest(){return triggerReason;}
bool benchActive(){return benchRaw.load();}
void trigger(uint32_t run,uint32_t seq,uint32_t at) {
 requestedClipSeq = 0;
 if(preparing.load() || stage.load()!=Normal){triggerReason="compare_probe_only";return;}
 triggerReason="unavailable";
 if(!enabled.load())return;
 flushPcm();
 if(ringN<PRE){++shortHistory;triggerReason="short_history";return;}
 // Only the DSP task fills these slots. flushPcm above publishes READY
 // before this scan when the last sample of the parent clip has arrived.
 if (wavEnabled.load() && !benchRaw.load()) {
  for (const auto& parent : clips) {
   if (parent.state.load() != FILLING) continue;
   if (parent.run != run || !parent.valid || !parent.wav || parent.rawBench) continue;
   const uint32_t ageMs = at - parent.trigger;
   const uint32_t postMs = (TOTAL - PRE) / 192;  // 192 PCM samples per ms
   if (ageMs >= postMs) continue;
   requestedClipSeq = parent.seq;
   triggerReason = "shared";
   return;
  }
 }
 for(auto& c:clips){uint8_t expected=FREE;
  portENTER_CRITICAL(&modelGate);bool claimed=!mutating&&c.state.compare_exchange_strong(expected,FILLING);portEXIT_CRITICAL(&modelGate);
  if(!claimed)continue;
  requestedClipSeq = seq;
  triggerReason=wavEnabled.load()?"armed":"score_only";
  c.passCfg=WildlifeDetector::passCurrent();c.test=false;c.rawBench=benchRaw.load() && wavEnabled.load();c.n=PRE;c.run=run;c.seq=seq;c.trigger=at;c.start=at-250;c.valid=true;c.active=activeMode.load();c.wav=wavEnabled.load();c.attempts=0;
  // Same DSP task owns pcm() and trigger(); no concurrent producer observes filling until return.
  size_t first=PRE-ringAt;memcpy(c.pcm,ring+ringAt,first*2);memcpy(c.pcm+first,ring,ringAt*2);return;}
 triggerReason="busy";++skipped;
}
void gap(){if(!enabled.load())return;flushPcm();ringAt=ringN=0;++gaps;for(auto& c:clips)if(c.state.load()==FILLING){c.valid=false;c.state.store(READY);}}
// Called once per PDM block. Returning a destination avoids a per-sample atomic load.
int16_t* testBlock(uint32_t endMs,size_t count,size_t& writable){
 ScanState expected=scanState.load();
 if(expected!=Sampling && expected!=Armed){writable=0;return nullptr;}
 if(expected==Armed && scanState.compare_exchange_strong(expected,Sampling))scan.start=endMs-(count*1000UL/192000UL);
 if(scanState.load()!=Sampling){writable=0;return nullptr;}
 lastSampleBlock=millis();writable=std::min(count,TOTAL-scan.n);return scan.pcm+scan.n;
}
void finishTestBlock(size_t written){
 scan.n+=written;
 if(scan.n==TOTAL){scan.captureComplete=missingSamples==0;scanState.store(Captured);}
}
void testGap(uint32_t blocks){
 if(scanState.load()!=Sampling)return;
 size_t fill=std::min<uint64_t>(TOTAL-scan.n,uint64_t(blocks)*1024);
 memset(scan.pcm+scan.n,0,fill*sizeof(int16_t));missingSamples+=fill;
 finishTestBlock(fill);
}
void endTestStream(){
 if(scanState.load()==Sampling){scan.captureComplete=false;scanState.store(Captured);}
}
void testAudioIdle(){
 if(scanState.load()==Sampling && millis()-lastSampleBlock>=3000UL)endTestStream();
}
void testTick(){
 uint32_t now=millis();
 if(bench && int32_t(now-benchEnd)>=0){preparing=false;stage.store(Normal);bench=false;benchRaw.store(false);period=0;WildlifeDay::autoMode();note("NZRT TEST bench=EXPIRED periodic=OFF");}
 if(period && int32_t(now-scanDue)>=0){scanDue=now+period;requestScan(true);}
 if(now-requestTime>15000){
   ScanState expected=Armed;
   if(scanState.compare_exchange_strong(expected,Empty))reportScan("FAILED_NO_AUDIO");
 }
 if(scanState.load()==Captured && !announced){
   Serial.printf("NZRT TEST_AUDIO seq=%lu samples=%lu zero_filled=%lu continuous=%u\n",(unsigned long)scan.seq,(unsigned long)scan.n,(unsigned long)missingSamples,scan.captureComplete);
   reportScan("CAPTURED");announced=true;
 }
}
bool compareCommand(const char* text){
 if(!strcmp(text,"prepare")){
   if(stage.load()!=Normal)return true;
   preparing=true;period=0;testCommand("test on");return true;
 }
 if(!strcmp(text,"stop")){
   stage.store(Normal);preparing=false;testCommand("test off");return true;
 }
 if(strcmp(text,"capture") && strcmp(text,"score") && strcmp(text,"send"))return false;
 if(stage.load()!=Normal || scanState.load()!=Empty || !idle() || !WildlifeTime::compareNetworkIdle()){
   Serial.println("NZRT COMPARE WAIT previous_audio_or_network");return true;
 }
 if(!preparing || !bench || period || !scan.pcm || !WildlifeTime::valid()){
   Serial.println("NZRT COMPARE UNAVAILABLE requires_bench_clock_buffer_and_scan_off");return true;
 }
 unsigned next=!strcmp(text,"capture")?Capture:!strcmp(text,"score")?Score:Send;
 issued=false;baseline=0;diagnosticSeq=0;stageStart=millis();stage.store(next);
 Serial.printf("NZRT COMPARE START stage=%s\n",stageName(next));return true;
}
void compareTick(){
 unsigned s=stage.load();
 if(s==Normal)return;
 uint32_t now=millis();
 if(!baseline && now-stageStart>=6000){
   baseline=now;WildlifeMic::compareCounters(true,stageName(s));
 }
 if(baseline && !issued && now-baseline>=2000){
   issued=true;
   if(requestScan(false))diagnosticSeq=scanId;
 }
 if(baseline && now-baseline>=20000){
   WildlifeMic::compareCounters(false,stageName(s));
   Serial.printf("NZRT COMPARE END stage=%s seq=%lu elapsed_ms=%lu\n",stageName(s),(unsigned long)diagnosticSeq,(unsigned long)(now-baseline));
   stage.store(Normal);
 }
}
void tick(){
 testTick();compareTick();
 for(auto& c:clips)if(c.state.load()==UPLOAD&&(!wavEnabled.load()||millis()-c.queued>300000UL)){
  char line[160];snprintf(line,sizeof(line),"NZRT WAV session=%08lx run=%lu seq=%lu result=DISCARDED reason=disabled_or_expired",(unsigned long)session,(unsigned long)c.run,(unsigned long)c.seq);note(line);c.state.store(FREE);
 }
 for(auto& c:clips)if(c.state.load()==RESULT){char line[768];
  if(c.rawBench){
   Serial.printf("NZRT BENCH_CANDIDATE session=%08lx run=%lu seq=%lu samples=%lu continuous=%d scoring=bypassed\n",(unsigned long)session,(unsigned long)c.run,(unsigned long)c.seq,(unsigned long)c.n,c.captureComplete);
   c.queued=millis();c.state.store(c.wav && wavEnabled.load() && c.n>PRE?UPLOAD:FREE);continue;
  }
  if(c.test){snprintf(line,sizeof(line),"NZRT ML_TEST result=%s synthetic=1 inference_us=%lu probability=%.9f model=%s",c.valid?"PASS":"FAIL",(unsigned long)c.us,c.probability,modelHash);note(line);c.state.store(FREE);continue;}
  const char* decision=!c.valid?"fallback_original":(c.probability>=c.threshold?"bat_candidate":"not_bat_candidate");
  snprintf(line,sizeof(line),"NZRT ML session=%08lx run=%lu seq=%lu model=%s feature_schema=1 clip_policy=pre250_post1750 mode=%s probability=%.9f threshold=%.9f valid=%u decision=%s inference_us=%lu start_uptime_ms=%lu utc_start=%lu samples=%lu sample_rate=192000 unverified=1",
   (unsigned long)session,(unsigned long)c.run,(unsigned long)c.seq,modelHash,c.active?"active":"shadow",c.probability,c.threshold,unsigned(c.valid),decision,(unsigned long)c.us,(unsigned long)c.start,(unsigned long)WildlifeTime::epochForUptime(c.start),(unsigned long)c.n);
  // The primary candidate has independent journal and live queues. A failed
  // auxiliary score write must not pin both PCM slots or strand a good WAV.
  WildlifeJournal::Writer f;bool saved=f&&f.println(line)>0&&f.close();
  Serial.println(line);
  if(!saved)Serial.printf("NZRT ML journal_failed run=%lu seq=%lu\n",(unsigned long)c.run,(unsigned long)c.seq);
  c.queued=millis();
  c.state.store(c.wav&&wavEnabled.load()&&c.captureComplete?UPLOAD:FREE);
 }
}
void status(Print& out){char pass[320];WildlifeDetector::passStatus(pass,sizeof(pass));out.println(pass);char b[512];snprintf(b,sizeof(b),"NZRT ML_STATUS enabled=%u model=%s mode=%s wav=%s completed=%lu skipped_busy=%lu short_history=%lu gaps=%lu wav_ack=%lu wav_failed=%lu network_failures=%lu model_pending=%u psram_bytes=%lu",
 unsigned(enabled.load()),modelHash,activeMode.load()?"active":"shadow",wavEnabled.load()?"on":"off",(unsigned long)completed.load(),(unsigned long)skipped.load(),(unsigned long)shortHistory.load(),(unsigned long)gaps.load(),(unsigned long)acked,(unsigned long)failed,(unsigned long)networkFailures,unsigned(fetchHash[0]!=0), (unsigned long)(PRE*2+TOTAL*4+RTFeatures::WORK_FLOATS*4+sizeof(RTModel::Model)));out.println(b);}
bool command(const char* line){
 if(!strncmp(line,"nzrt pass ",10)){passCommand(String(line+5));return true;}
 if(!strcmp(line,"nzrt overlap test")){
  if(!enabled.load()){note("NZRT OVERLAP unavailable");return true;}
  Mutation mutation;
  if(!mutation.ok){note("NZRT OVERLAP busy");return true;}
  Clip& c=clips[0];
  c.state.store(SCORING);
  c.test=true;c.n=TOTAL;c.run=0;c.seq=UINT32_MAX;c.rawBench=false;c.valid=true;
  // Repeatable wideband input with bursts. Same PCM for both passes.
  uint32_t random=123;
  for(size_t i=0;i<TOTAL;++i){
   random=random*1664525u+1013904223u;
   int32_t sample=int32_t(random>>16)-32768;
   c.pcm[i]=int16_t(sample/(i%19200<1800?4:128));
  }
  note("NZRT OVERLAP queued");c.state.store(READY);return true;
 }

 if(!strncmp(line,"nzrt compare ",13))return compareCommand(line+13);
 if(!strcmp(line,"nzrt test status")){
  const char* states[]={"idle","waiting_audio","recording","awaiting_receiver"};
  Serial.printf("NZRT TEST_STATUS bench=%d period_s=%lu state=%s seq=%lu buffer=%d last=%s\n",bench,(unsigned long)(period/1000),states[scanState.load()],(unsigned long)scanId,scan.pcm!=nullptr,lastScanEvent);
  return true;
 }
 if(!strncmp(line,"nzrt ",5) && (!strcmp(line+5,"record now") || !strcmp(line+5,"test on") || !strcmp(line+5,"test off") || !strncmp(line+5,"scan ",5))){testCommand(line+5);return true;}
 if(strcmp(line,"nzrt ml status")==0){status();return true;}
 if(strcmp(line,"nzrt ml test")==0){
  if(!enabled.load()||!WildlifeMic::daytimeStandby()){note("NZRT ML_TEST rejected requires_enabled_daytime_idle=1");return true;}
  Mutation mutation;if(!mutation.ok){note("NZRT ML_TEST rejected busy=1");return true;}
  Clip& c=clips[0];c.state.store(SCORING);c.test=true;c.rawBench=false;c.n=TOTAL;c.run=c.seq=0;c.start=c.trigger=millis();c.valid=true;c.active=false;c.wav=false;c.attempts=0;
  memset(c.pcm,0,TOTAL*2);c.state.store(READY);note("NZRT ML_TEST queued synthetic=1");return true;
 }
 if(strcmp(line,"nzrt wav on")==0||strcmp(line,"nzrt wav off")==0){bool on=strcmp(line,"nzrt wav on")==0;
  if(saveBool("wav",on)){wavEnabled=on;note(on?"NZRT WAV enabled":"NZRT WAV disabled");}else note("NZRT CONFIG failed=NVS");return true;}
 if(strcmp(line,"nzrt ml shadow")==0||strcmp(line,"nzrt ml active")==0){bool active=strcmp(line,"nzrt ml active")==0;
  if(active&&!enabled.load()){note("NZRT MODEL promotion_failed unavailable");return true;}
  Preferences p;bool ok=p.begin("nzrt-ml",false);if(ok){ok=p.putString("promoted",active?modelHash:"")>0;p.end();}
  if(ok){activeMode=active;note(active?"NZRT MODEL mode=active original_candidates_retained=1":"NZRT MODEL mode=shadow");}else note("NZRT CONFIG failed=NVS");return true;}
 if(strncmp(line,"nzrt model fetch ",17)==0){const char* h=line+17;bool valid=strlen(h)==64;
  for(size_t i=0;valid&&i<64;++i)valid=(h[i]>='0'&&h[i]<='9')||(h[i]>='a'&&h[i]<='f');
  if(valid&&enabled.load()){
   Preferences p;bool ok=p.begin("nzrt-ml",false);if(ok){ok=p.putString("fetch",h)>0;p.end();}
   if(ok){strcpy(fetchHash,h);nextNet=0;note("NZRT MODEL queued requires_daytime_idle=1");}else note("NZRT CONFIG failed=NVS");
  }else note("NZRT MODEL invalid_sha_or_unavailable");return true;}
 if(strcmp(line,"nzrt model builtin")==0){if(!WildlifeMic::daytimeStandby()||!idle()){note("NZRT MODEL busy requires_daytime_idle=1");return true;}
  Mutation mutation;if(!mutation.ok||!model){note("NZRT MODEL unavailable_or_busy");return true;}Preferences p;bool ok=p.begin("nzrt-ml",false);if(ok){ok=p.putString("selection","")>0;p.putString("promoted","");p.remove("fetch");p.end();}
  if(ok){RTModel::builtin(*model);strcpy(modelHash,"builtin-wav-mlp-v01");modelSlot=-1;activeMode=false;fetchHash[0]=0;note("NZRT MODEL builtin mode=shadow");}return true;}
 return false;
}
bool testUploadDue(){return scanState.load()==Captured && int32_t(millis()-nextScanAttempt)>=0;}
bool wantsNetwork(){
 for(auto& c:clips)if(c.state.load()==UPLOAD&&!wavEnabled.load())c.state.store(FREE);
 if(scanState.load()==Captured && int32_t(millis()-nextScanAttempt)>=0)return true;
 if(int32_t(millis()-nextNet)<0)return false;
 if(int32_t(millis()-nextControl)>=0)return true;
 if(fetchHash[0]&&WildlifeMic::daytimeStandby()&&idle())return true;
 if(wavEnabled.load())for(auto& c:clips)if(c.state.load()==UPLOAD)return true;
 return false;
}
void connected(){
 if(int32_t(millis()-nextControl)>=0)pollControl();
 if(scanState.load()==Captured && int32_t(millis()-nextScanAttempt)>=0){
   if(!announced)testTick();
   if(upload(scan)){reportScan("ACK");scanState.store(Empty);}
   else {reportScan("RETRY");nextScanAttempt=millis()+30000UL;}
   return;
 }
 if(fetchHash[0]&&WildlifeMic::daytimeStandby()&&idle()){
  bool ok=fetchModel();note(ok?"NZRT MODEL fetch=ACK":"NZRT MODEL fetch=FAILED old_model_retained=1");
  Preferences p;if(p.begin("nzrt-ml",false)){p.remove("fetch");p.end();}
  fetchHash[0]=0;nextNet=millis()+60000;return;}
 for(auto& c:clips)if(c.state.load()==UPLOAD){bool ok=wavEnabled.load()&&upload(c);if(ok)++acked;else ++failed;
  char line[192];snprintf(line,sizeof(line),"NZRT WAV session=%08lx run=%lu seq=%lu result=%s attempt=%u",(unsigned long)session,(unsigned long)c.run,(unsigned long)c.seq,ok?"ACK":"FAILED",unsigned(++c.attempts));note(line);
  if(ok||c.attempts>=3||!wavEnabled.load())c.state.store(FREE);nextNet=millis()+(ok?1000:60000);return;}
}
void networkFailed(){
 if(scanState.load()==Captured){reportScan("WIFI_CONNECT_RETRY");nextScanAttempt=millis()+30000UL;}
 ++networkFailures;bool clipsWaiting=false;
 for(auto& c:clips)if(c.state.load()==UPLOAD){
  if(++c.attempts>=3){char line[160];snprintf(line,sizeof(line),"NZRT WAV session=%08lx run=%lu seq=%lu result=DISCARDED reason=connection_retries",(unsigned long)session,(unsigned long)c.run,(unsigned long)c.seq);note(line);c.state.store(FREE);}else clipsWaiting=true;
 }
 if(int32_t(millis()-nextControl)>=0)nextControl=millis()+pollInterval();
 uint32_t retry=clipsWaiting?60000UL:(fetchHash[0]?900000UL:pollInterval());nextNet=millis()+retry;
 char line[96];snprintf(line,sizeof(line),"NZRT WIFI_OPTIONAL network=FAILED retry_seconds=%lu",(unsigned long)(retry/1000));note(line);
}
}
