"""Exact PASS-1 input only. No credentials, radio or existing threshold edits."""
from pathlib import Path
import hashlib
HERE=Path(__file__).resolve().parent
BASE={'WildlifeDetector.cpp':'bdbd8dc776bdf52303fc6b5cc9b5e458cba056b20038d03480245172cc1e54f7','WildlifeMic.cpp':'6ca6bff4abbc214ba391e02f0a2459ecc5e7ee89f0089cde49f6b5febdbc260b','WildlifeML.cpp':'a3105a42651021715e0eeaa2cc8cd8667fe6515c3cf5f200d0a5a649ec82b6f9','WildlifeUpload.h':'50dff9943ae8e7bbd2583be4fc4c04d961acbe3d6b197ab06fcd77ee8c685471','WildlifeDetector.h':'69c289f42e38e8b967c9a540d21eadba78b1cc8bad953da9cd476c9f6226e598'}
def digest(t):return hashlib.sha256(t.encode()).hexdigest()
def one(s,a,b):
    if s.count(a)!=1:raise ValueError('release source anchor differs: '+a[:60])
    return s.replace(a,b)
def guard1(name,s):
    if digest(s)!=BASE[name]:raise ValueError('unknown PASS-1 source: '+name)
    s=s.replace('NZRT-J4-PASS-1','NZRT-J4-GUARD-1')
    if name=='WildlifeDetector.cpp':
        s=one(s,'#include <cmath>','#include "GuardSignals.h"\n#include <cmath>')
        s=one(s,'static bool measureScore=false;', '''// Only the DSP task writes these. Pressure only drops optional comparison work.
static bool queuePressure=false,shadowDirty=false,eventShadowGap=false;
static unsigned lastShadow=0;
static uint32_t holdWindows=0;
void clearShadow(unsigned n){
 if(n==2){FirstPass::warmE=0;for(auto& b:FirstPass::bands)b.z1=b.z2=0;}
 if(n==3){auto p=FirstPass::audible.load();if(p){p->warm=0;p->bg[0]=p->bg[1]=0;}}
}
static bool measureScore=false;''')
        s=one(s,'namespace {\n// NZ band monitor','static bool queuePressure=false;\nvoid guardPressure(bool pressure){queuePressure=pressure;}\nnamespace {\n// NZ band monitor')
        s=one(s,'static bool queuePressure=false,shadowDirty=false,eventShadowGap=false;','static bool shadowDirty=false,eventShadowGap=false;')
        s=one(s,'unsigned selected=cfg&3, shadow=cfg>>2;', '''unsigned selected=cfg&3, shadow=cfg>>2;
   if(shadow!=lastShadow){lastShadow=shadow;shadowDirty=false;holdWindows=0;}
   const unsigned requestedShadow=shadow;
   if(shadow>=2 && (queuePressure||holdWindows||optionalHoldSamples)){
     if(holdWindows)--holdWindows;
     shadow=0;shadowDirty=true;RtWatch::bump(RtWatch::sig().held);
   }else if(shadowDirty){clearShadow(shadow);shadowDirty=false;}''')
        s=one(s,'lastPassUs.store(dt);','lastPassUs.store(dt);\n   if(shadow>=2 && dt>=5000)holdWindows=250; // 5 s after expensive optional work')
        s=one(s,'eventPass=cfg;eventShadow=false;','eventPass=cfg;eventShadow=false;eventShadowGap=false;')
        s=one(s,'eventShadow|=shadowHit;','eventShadow|=shadowHit;eventShadowGap|=requestedShadow!=shadow;')
        s=one(s,'e.passConfig=eventPass;e.shadowMatched=eventShadow;', 'e.passConfig=eventPass;e.shadowMatched=eventShadow;e.shadowIncomplete=eventShadowGap;')
        s=one(s,'uint32_t firstOn=0,lastOn=0;','uint32_t firstOn=0,lastOn=0;\nbool eventShadowGap=false;');s=one(s,'static bool shadowDirty=false,eventShadowGap=false;','static bool shadowDirty=false;')
        s=one(s,'++windows;\n uint32_t t=', '++windows; RtWatch::bump(RtWatch::sig().win);\n uint32_t t=')
        s=one(s,'if(!preparePass(cfg))return false;', 'if(RtWatch::sig().forceLegacy.load() && cfg!=0)return false;\n if(!preparePass(cfg))return false;')
        s=one(s,'FirstPass::clear();\n initMoments();','FirstPass::clear();holdWindows=0;shadowDirty=false;queuePressure=false;\n initMoments();')
        s=one(s,'Band bands[]={{18000,24000},{24000,27000},{27000,33000},{36000,44500}};',
            'using Bank=Band[4]; Bank& bands(){static Bank bank={{18000,24000},{24000,27000},{27000,33000},{36000,44500}};return bank;}')
        s=s.replace('b=bands[k]','b=bands()[k]').replace('b:bands)','b:bands())').replace('b:FirstPass::bands)','b:FirstPass::bands())')
        s=one(s,'WildlifeScoring::Analyzer scorer;', 'WildlifeScoring::Analyzer& scorer(){static WildlifeScoring::Analyzer state;return state;}').replace('scorer.', 'scorer().')
    elif name=='WildlifeDetector.h':
        s=one(s,'const char* passName(unsigned);','void guardPressure(bool pressure);\nconst char* passName(unsigned);')
        s=one(s,'bool shadowMatched;','bool shadowMatched;bool shadowIncomplete;')
    elif name=='WildlifeMic.cpp':
        s=one(s,'#include "WildlifeMic.h"','#include "GuardSignals.h"\n#include <esp_attr.h>\n#include "WildlifeMic.h"')
        # Shared across reader, DSP, reporter and supervisor.
        for n in ('captureEnabledRequest','dspEnabledRequest','dayStandby','captureRunning'):
            s=one(s,'volatile bool '+n,'std::atomic<bool> '+n)
        for n in ('dspRunNumber','dspStartUptimeMs'):s=one(s,'volatile uint32_t '+n,'std::atomic<uint32_t> '+n)
        import re
        s=re.sub(r'(std::atomic<(?:bool|uint32_t)> \w+) = (true|false|0);',r'\1{\2};',s)
        s=one(s,'bool started = false;','bool started = false;\n'+(HERE/'guard_task.inc').read_text())
        s=one(s,'if(status==ESP_OK && n)emptyReads=0;', 'if(status==ESP_OK && n==sizeof(pkt.words)) {emptyReads=0;RtWatch::bump(RtWatch::sig().rd);}')
        s=one(s,'int64_t before=esp_timer_get_time();\n    WildlifeDetector::consume','WildlifeDetector::guardPressure(RtWatch::pressure(uxQueueMessagesWaiting(dspQueue),poolCapacity));\n    int64_t before=esp_timer_get_time();\n    WildlifeDetector::consume')
        s=one(s,'++stats.dspBlocksProcessed;', '++stats.dspBlocksProcessed;RtWatch::bump(RtWatch::sig().dp);')
        s=one(s,'  started = true;', '''  // Do not reset all acquisition if optional supervisor allocation fails.
  bool recovered=esp_reset_reason()==ESP_RST_SW && RtGuard::valid(guardRTC);
  if(!recovered)guardRTC={0,0,0};
  guardPolicy.spent=recovered;
  RtWatch::sig().previous.store(recovered?guardRTC.reason:0);
  RtWatch::sig().forceLegacy.store(recovered);
  if(recovered) WildlifeDetector::requestPass(0);
  RtWatch::sig().starting.store(true);
  bool guardOnline=xTaskCreatePinnedToCore(guardTask,"rt_guard",3072,nullptr,3,nullptr,1)==pdPASS;
  started = true;''')
        s=one(s,'  dspEnabledRequest = true;\n  return true;', '''  dspEnabledRequest = true;
  RtWatch::sig().ready.store(guardOnline);
  RtWatch::sig().starting.store(false);
  Serial.printf("NZRT GUARD online=%u recovery=%u previous_fault=%u\\n",unsigned(guardOnline),unsigned(recovered),RtWatch::val(RtWatch::sig().previous));
  return true;''')
        # On supervised recovery, start baseline before any optional boot logging.
        s=one(s,'  Serial.println("NZRT MIC experimental legacy I2S:', '  if(recovered){dspEnabledRequest=true;RtWatch::sig().ready.store(guardOnline);RtWatch::sig().starting.store(false);return true;}\n  Serial.println("NZRT MIC experimental legacy I2S:')
        s=one(s,'  WildlifeML::status();\n  WildlifeJournal::status();','  Serial.printf("NZRT GUARD online=%u previous_fault=%u safe=%u fault=%u shadow_skipped=%u\\n",unsigned(RtWatch::sig().ready.load()),RtWatch::val(RtWatch::sig().previous),unsigned(RtWatch::sig().forceLegacy.load()),RtWatch::val(RtWatch::sig().fault),RtWatch::val(RtWatch::sig().held));\n  WildlifeML::status();\n  WildlifeJournal::status();')
        s=one(s,'  WildlifeML::tick();','  RtWatch::bump(RtWatch::sig().rep);\n  WildlifeML::tick();')
        s=one(s,'if(degraded || wasDegraded || !lastHealth','if(RtWatch::val(RtWatch::sig().fault) || degraded || wasDegraded || !lastHealth')
        s=one(s,'live_dropped=%lu\\n','live_dropped=%lu guard_online=%u guard_fault=%u previous_fault=%u safe=%u shadow_skipped=%u\\n')
        s=one(s,'(unsigned long)liveDropped);\n      Serial.print(liveHealth);','(unsigned long)liveDropped,unsigned(RtWatch::sig().ready.load()),RtWatch::val(RtWatch::sig().fault),RtWatch::val(RtWatch::sig().previous),unsigned(RtWatch::sig().forceLegacy.load()),RtWatch::val(RtWatch::sig().held));\n      Serial.print(liveHealth);')
        s=one(s,'char liveHealth[256]', 'char liveHealth[448]')
        s=one(s,'pass_shadow_hit=%u unverified','pass_shadow_hit=%u shadow_complete=%u unverified')
        s=one(s,'unsigned(ev.shadowMatched));','unsigned(ev.shadowMatched),unsigned(!ev.shadowIncomplete && (ev.passConfig>>2)!=0));')
    elif name=='WildlifeML.cpp':
        s=one(s,'#include "WildlifeML.h"','#include "GuardSignals.h"\n#include "WildlifeML.h"')
        s=one(s,'if(!WildlifeDetector::preparePass(cfg))','if(RtWatch::sig().forceLegacy.load() && cfg!=0){note("NZRT GUARD selection_locked_until_power_cycle");return false;}\n   if(!WildlifeDetector::preparePass(cfg))')
        s=one(s,' session=id;',' session=id;\n if(RtWatch::sig().forceLegacy.load()){WildlifeDetector::requestPass(0);note("NZRT GUARD recovery=legacy_only ml=off wav=off prefs_preserved=1");return false;}')
        s=one(s,' {Preferences p;if(p.begin("nzrt-ml",true)){unsigned cfg=p.getUInt("pass1",8);',' if(!RtWatch::sig().forceLegacy.load()){Preferences p;if(p.begin("nzrt-ml",true)){unsigned cfg=p.getUInt("pass1",8);')
        s=one(s,'void tick(){\n testTick();','void tick(){\n if(RtWatch::sig().forceLegacy.load())return;\n testTick();')
        s=one(s,'bool command(const char* line){','bool command(const char* line){\n if(RtWatch::sig().forceLegacy.load())return false;')
        s=one(s,'bool wantsNetwork(){','bool wantsNetwork(){\n if(RtWatch::sig().forceLegacy.load())return false;')
    return s

def transform(name,s):
    from guard2 import upgrade
    return upgrade(name,guard1(name,s))
