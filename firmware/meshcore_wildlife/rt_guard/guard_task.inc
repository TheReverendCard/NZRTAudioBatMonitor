// Independent from MeshCore's main loop, HTTP, filesystem and the DSP task.
RTC_NOINIT_ATTR static RtGuard::Record guardRTC;
static RtGuard::Policy guardPolicy;
static void guardTask(void*) {
 for(;;){
   auto& t=RtWatch::sig();
   bool on=t.ready.load() && captureEnabledRequest && dspEnabledRequest && !dayStandby;
   RtGuard::Inputs sample={dspRunNumber,RtWatch::val(t.rd),RtWatch::val(t.dp),
     RtWatch::val(t.win),RtWatch::val(t.rep),on,WildlifeML::compareStage()!=1};
   // Hardware and tasks exist here, but an optional journal/ML call may
   // block before normal monitoring is armed. Watch that path independently.
   static bool waiting=false;static uint32_t entered=0;
   bool starting=t.starting.load();
   if(starting && !waiting)entered=millis();
   waiting=starting;
   auto decision=guardPolicy.sample(millis(),sample);
   if(starting && uint32_t(millis()-entered)>=180000){
     decision.fault=RtGuard::Reporter;
     if(!guardPolicy.spent){guardPolicy.spent=true;decision.restart=true;}
   }
   t.fault.store(decision.fault);
   if(decision.restart){
     guardRTC=RtGuard::record(decision.fault);
     __sync_synchronize();
     esp_restart();
   }
   vTaskDelay(pdMS_TO_TICKS(1000));
 }
}
