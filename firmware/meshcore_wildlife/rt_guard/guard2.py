"""Apply GUARD-2 to the pinned GUARD-1 transformation, leaving the source private."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
def one(s,a,b):
 if s.count(a)!=1:raise ValueError('GUARD-2 source differs: '+a[:70])
 return s.replace(a,b)
def region(s,a,b,repl):
 i=s.index(a);j=s.index(b,i);return s[:i]+repl+s[j:]
def upgrade(n,s):
 s=s.replace('NZRT-J4-GUARD-1','NZRT-J4-GUARD-2')
 if n=='WildlifeDetector.cpp':
  s=one(s,'namespace FirstPass {','''constexpr uint32_t BUDGET_US=5000;
uint32_t passClock();
inline bool deadline(uint32_t start){return uint32_t(passClock()-start)>=BUDGET_US;}
namespace FirstPass {''')
  s=one(s,'if(!preparePass(cfg))return false;desiredPass.store(cfg);return true;', 'if(!preparePass(cfg))return false;\n desiredPass.store(cfg);return true;')
  s=one(s,'bool evolved(const float* pcm){','bool evolved(const float* pcm,uint32_t startUs,bool& complete){')
  s=one(s,'for(unsigned i=start;i<start+1920;++i){float y=b.step(pcm[i]);sum+=y*y;}','''for(unsigned i=start;i<start+1920;i+=240){
       if(deadline(startUs)){complete=false;return hot;}
       for(unsigned j=i;j<i+240;++j){float y=b.step(pcm[j]);sum+=y*y;}
     }''')
  s=one(s,'out[960]','out[480]')
  s=region(s,' void transform(',' bool check(', (HERE/'fast_real_fft.inc').read_text())
  s=one(s,'bool check(const float* pcm){','bool check(const float* pcm,uint32_t startUs,bool& complete){')
  s=one(s,'transform(out,960,1,input);','if(!transform(out,480,2,input,startUs)){complete=false;return hot;}')
  s=s.replace('out[i].r*out[i].r+out[i].i*out[i].i','power(i)')
  s=one(s,'if((cfg&3)>2 || cfg>14 || (cfg>>2)==(cfg&3)+1)return false;', 'if(cfg>31 || (cfg&3)>2 || ((cfg>>2)&3)==(cfg&3)+1 || ((cfg&16) && !(cfg&3)))return false;')
  s=s.replace('(cfg>>2)==3','((cfg>>2)&3)==3')
  s=one(s,'unsigned eventPass=', '''std::atomic<unsigned> newReady{0},baseCoverage{0},newOnly{0},legacyRescue{0},overBudget{0};
void coverage(char* b,size_t n){snprintf(b,n,"new_ready=%u fallback_windows=%u new_only=%u legacy_rescue=%u over_budget=%u",newReady.load(),baseCoverage.load(),newOnly.load(),legacyRescue.load(),overBudget.load());}
unsigned eventMask=0;bool eventFallback=false;
unsigned eventPass=''')
  s=s.replace('version=PASS-1 active=%s','version=PASS-2 active=%s')
  s=one(s,'worst_us=%u",','worst_us=%u assist=%u requested_assist=%u",')
  s=one(s,'maxPassUs.load());','maxPassUs.load(),(cfg>>4)&1,(want>>4)&1);')
  for v in ('cfg','want'):s=s.replace(f'({v}>>2)?passName(({v}>>2)-1)',f'(({v}>>2)&3)?passName((({v}>>2)&3)-1)')
  s=region(s,'static bool shadowDirty=', 'void clearShadow(','''static unsigned skips[3]={},cooldown[3]={};
void resetBudget(){for(unsigned i=0;i<3;i++){skips[i]=0;cooldown[i]=0;}}
''')
  s=one(s,'static bool queuePressure=false;', '''#ifdef NZRT_HOST_TEST
static uint32_t clockStep=0;
uint32_t passClock(){static uint32_t t=0;t+=clockStep;return t;}
#else
uint32_t passClock(){return uint32_t(esp_timer_get_time());}
#endif
static bool queuePressure=false;''')
  s=one(s,'FirstPass::clear();appliedPass.store(cfg);' ,'FirstPass::clear();resetBudget();appliedPass.store(cfg);')
  s=region(s,'   unsigned selected=cfg&3','   if(hot) {',(HERE/'pass2_window.inc').read_text())
  s=one(s,'eventPass=cfg;eventShadow=false;', 'eventPass=cfg;eventMask=0;eventFallback=false;eventShadow=false;')
  s=one(s,'eventShadow|=shadowHit;eventShadowGap|=requestedShadow!=shadow;', 'eventMask|=source;eventFallback|=provisional;eventShadow|=shadowHit;eventShadowGap|=shadow && !evaluated[shadow-1];')
  s=one(s,'e.passConfig=eventPass;', 'e.triggerMask=eventMask;e.fallback=eventFallback;e.passConfig=eventPass;')
  s=one(s,'holdWindows=0;shadowDirty=false;', 'resetBudget();')
  s=one(s,'// Host replay uses', '''void setCostForTest(uint32_t step){clockStep=step;}
void spectrumForTest(const float* x,float* result){
 static FirstPass::Audible a;
 for(int j=0;j<960;++j)a.input[j]=x[j]*a.window[j];
 a.transform(a.out,480,2,a.input,passClock());
 for(int k=1;k<480;++k)result[k]=a.power(k);
}
// Host replay uses''')
 if n=='WildlifeDetector.h':
  s=one(s,'void passStatus','void coverage(char*,size_t);\nvoid passStatus')
  s=one(s,'unsigned passConfig;', 'unsigned passConfig;uint8_t triggerMask;bool fallback;')
  s=one(s,'void consumePcmForTest', 'void setCostForTest(uint32_t);\nvoid spectrumForTest(const float*,float*);\nvoid consumePcmForTest')
 if n=='WildlifeML.cpp':
  s=one(s,'if(cmd!=String("pass ")+','const bool assist=cmd.startsWith("pass assist ");\n   if(assist && !a)continue;\n   if(cmd!=String(assist?"pass assist ":"pass ")+')
  s=s.replace('char msg[320]', 'char msg[448]').replace('char pass[320]', 'char pass[448]')
  s=one(s,'unsigned cfg=p.getUInt("pass1",8);','unsigned cfg=p.getUInt("pass2",p.getUInt("pass1",8));')
  s=s.replace('p.getUInt("pass1",255)','p.getUInt("pass2",255)').replace('p.putUInt("pass1",cfg)','p.putUInt("pass2",cfg)')
  s=one(s,'unsigned cfg=a+4*s;', 'unsigned cfg=a+4*s+(assist?16:0);')
  s=one(s,'if(!diagnostic)http.addHeader("X-First-Pass"', 'if(!diagnostic)http.addHeader("X-Pass-Policy",(c.passCfg&16)?"assist":"selected");\n if(!diagnostic)http.addHeader("X-First-Pass"')
 if n=='WildlifeMic.cpp':
  s=s.replace('(ev.passConfig>>2)','((ev.passConfig>>2)&3)')
  s=one(s,'shadow_complete=%u unverified','shadow_complete=%u assist=%u trigger_mask=%u fallback=%u unverified')
  s=one(s,'((ev.passConfig>>2)&3)!=0));','((ev.passConfig>>2)&3)!=0),unsigned((ev.passConfig&16)!=0),unsigned(ev.triggerMask),unsigned(ev.fallback));')
  s=one(s,'      snprintf(liveHealth,sizeof(liveHealth),\n        "NZRT FIELD health=1 session=', '      char coverage[160];WildlifeDetector::coverage(coverage,sizeof(coverage));\n      snprintf(liveHealth,sizeof(liveHealth),\n        "NZRT FIELD health=1 session=')
  s=one(s,'safe=%u shadow_skipped=%u\\n",\n        (unsigned long)sessionId','safe=%u shadow_skipped=%u %s\\n",\n        (unsigned long)sessionId')
  s=one(s,'RtWatch::val(RtWatch::sig().held));\n      Serial.print(liveHealth);','RtWatch::val(RtWatch::sig().held),coverage);\n      Serial.print(liveHealth);')
 return s
