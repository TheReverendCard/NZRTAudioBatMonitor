void tick(){
 if(RtWatch::sig().forceLegacy.load())return;
 testTick();compareTick();loadTick();
 for(auto& c:clips){
  if(c.state.load()==READY){
   c.captureComplete=c.valid && c.n==TOTAL;
   c.queued=millis();c.us=c.featureUs=c.modelUs=c.waitUs=c.chunkUs=0;c.probability=NAN;
   c.threshold=model->threshold;
   bool needScore=c.captureComplete && !c.rawBench && (inferenceEnabled.load()||c.test);
   c.scoreReason=!c.captureComplete?"incomplete_audio":c.rawBench?"raw_bench":!needScore?"disabled":"pending";
   c.lease.publish(needScore,!c.test && c.captureComplete && c.wav && wavEnabled.load());
   if(!needScore){c.valid=false;++scoreSkipped;}
   c.state.store(OWNED); // immutable PCM and metadata published to both consumers
  }
  if(c.state.load()!=OWNED)continue;
  if(c.lease.delivery && (!wavEnabled.load() || millis()-c.queued>300000UL)){
   char line[192];snprintf(line,sizeof(line),"NZRT %s session=%08lx run=%lu seq=%lu result=DISCARDED reason=disabled_or_expired",
    c.loadProbe?"LOAD_WAV":"WAV",(unsigned long)session,(unsigned long)c.run,(unsigned long)c.seq);note(line);c.lease.delivery=false;
  }
  if(c.lease.score.load()==RTClipLease::Done){
   char line[1024];
   if(c.test && c.seq==UINT32_MAX){ /* overlap command already reported */ }
   else if(c.rawBench){Serial.printf("NZRT BENCH_CANDIDATE session=%08lx run=%lu seq=%lu samples=%lu continuous=%d scoring=bypassed\n",
     (unsigned long)session,(unsigned long)c.run,(unsigned long)c.seq,(unsigned long)c.n,c.captureComplete);}
   else if(c.test){snprintf(line,sizeof(line),"NZRT ML_TEST result=%s synthetic=1 inference_us=%lu probability=%.9f model=%s",c.valid?"PASS":"FAIL",(unsigned long)c.us,c.probability,modelHash);note(line);}
   else {
    const char* decision=!c.valid?"fallback_original":c.probability>=c.threshold?"bat_candidate":"not_bat_candidate";
    snprintf(line,sizeof(line),"NZRT %s session=%08lx run=%lu seq=%lu model=%s feature_schema=1 clip_policy=pre250_post1750 mode=%s probability=%.9f threshold=%.9f valid=%u decision=%s inference_us=%lu feature_us=%lu model_us=%lu explicit_wait_us=%lu checkpoint_peak_us=%lu score_reason=%s start_uptime_ms=%lu utc_start=%lu samples=%lu sample_rate=192000 unverified=1",
     c.loadProbe?"LOAD_ML":"ML",(unsigned long)session,(unsigned long)c.run,(unsigned long)c.seq,modelHash,c.active?"active":"shadow",c.probability,c.threshold,unsigned(c.valid),decision,
     (unsigned long)c.us,(unsigned long)c.featureUs,(unsigned long)c.modelUs,(unsigned long)c.waitUs,(unsigned long)c.chunkUs,c.scoreReason,
     (unsigned long)c.start,(unsigned long)WildlifeTime::epochForUptime(c.start),(unsigned long)c.n);
    note(line);
   }
   c.lease.score.store(RTClipLease::Reported);
  }
  if(c.lease.releasable())c.state.store(FREE);
 }
}
