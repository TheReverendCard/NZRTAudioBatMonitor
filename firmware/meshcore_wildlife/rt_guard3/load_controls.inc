void controlStatus(char* msg,size_t n){
 snprintf(msg,n,"NZRT WORK inference=%u wav=%u mode=%s load=%u load_running=%u interval_s=10 period_s=%lu bench=%u idle=%u valid=%lu skipped=%lu probes=%lu probe_busy=%lu",
  unsigned(inferenceEnabled.load()),unsigned(wavEnabled.load()),activeMode.load()?"active":"shadow",unsigned(loadActive),unsigned(loadRunning),
  (unsigned long)(period/1000),unsigned(bench),unsigned(idle()),(unsigned long)scoreValid.load(),(unsigned long)scoreSkipped.load(),(unsigned long)(loadSeq.load()-0x80000000UL),(unsigned long)loadBusy.load());
}
bool workCommand(const String& cmd){
 if(cmd=="health status"){char b[512];controlStatus(b,sizeof(b));Serial.println(b);WildlifeJournal::ramStatus(b,sizeof(b),session);Serial.println(b);return true;}
 if(cmd!="infer on" && cmd!="infer off")return false;
 if(loadActive){note("NZRT WORK rejected=load_test_active");return false;}
 bool on=cmd=="infer on";
 if(!saveBool("infer",on)){note("NZRT WORK rejected=NVS");return false;}
 inferenceEnabled=on;char b[512];controlStatus(b,sizeof(b));note(b);return true;
}
void loadStop(){
 loadRunning=false;loadRequest.store(false);
 if(!loadActive)return;
 loadActive=false;inferenceEnabled=savedInference;wavEnabled=savedWav;activeMode=savedActive;
 bench=false;benchRaw=false;period=0;WildlifeDay::autoMode();
 note("NZRT LOAD stopped=1 settings_restored=1 schedule=auto");
}
bool loadCommand(const char* cmd){
 if(!strcmp(cmd,"status")){char b[512];controlStatus(b,sizeof(b));Serial.println(b);return true;}
 if(!strcmp(cmd,"start")){
  if(loadActive || bench || period || preparing || stage.load()!=Normal || !enabled || !WildlifeTime::valid() || !idle()){
   note("NZRT LOAD rejected=requires_idle_clock_normal_mode");return true;}
  savedInference=inferenceEnabled;savedWav=wavEnabled;savedActive=activeMode;
  loadActive=true;loadRunning=false;loadEnd=millis()+3600000UL;
  bench=true;benchEnd=loadEnd;benchRaw=false;activeMode=false;
  WildlifeDay::benchWake(3600);nextControl=nextNet=0;
  note("NZRT LOAD started=1 max_seconds=3600 real_scoring=1");return true;
 }
 if(!strcmp(cmd,"stop")){loadStop();return true;}
 if(!loadActive){note("NZRT LOAD rejected=not_started");return true;}
 if(!strcmp(cmd,"pause")){loadRunning=false;loadRequest=false;note("NZRT LOAD paused=1");return true;}
 if(!strcmp(cmd,"finish")){
  if(loadRunning || !idle()){note("NZRT LOAD WAIT drain_pending");return true;}
  WildlifeMic::compareCounters(false,loadPhase);note("NZRT LOAD finished=1");return true;
 }
 if(!strncmp(cmd,"phase ",6) && strlen(cmd)==9 && (cmd[6]=='0'||cmd[6]=='1') && cmd[7]==' ' && (cmd[8]=='0'||cmd[8]=='1')){
  if(loadRunning || !idle()){note("NZRT LOAD WAIT drain_pending");return true;}
  inferenceEnabled=cmd[6]=='1';wavEnabled=cmd[8]=='1';
  snprintf(loadPhase,sizeof(loadPhase),"load%c%c",cmd[6],cmd[8]);
  WildlifeMic::compareCounters(true,loadPhase);loadNext=millis()+3000;loadRunning=true;
  Serial.printf("NZRT LOAD phase=%s inference=%u wav=%u\n",loadPhase,unsigned(inferenceEnabled.load()),unsigned(wavEnabled.load()));return true;
 }
 note("NZRT LOAD rejected=unknown");return true;
}
void loadTick(){
 if(!loadActive)return;
 if(int32_t(millis()-loadEnd)>=0){loadStop();return;}
 if(loadRunning && int32_t(millis()-loadNext)>=0){loadRequest=true;loadNext=millis()+10000;}
}
