struct ScoreBudget {
 Clip& clip; int64_t started=esp_timer_get_time(),lastYield=started,lastCheck=started;
 uint32_t wait=0,peakChunk=0;
 explicit ScoreBudget(Clip& c):clip(c){}
 static bool check(void* ptr) {
  auto& b=*static_cast<ScoreBudget*>(ptr);int64_t now=esp_timer_get_time();
  b.peakChunk=std::max(b.peakChunk,uint32_t(now-b.lastCheck));b.lastCheck=now;
  if(!b.clip.test && !inferenceEnabled.load()){b.clip.scoreReason="disabled";return false;}
  if(RtWatch::sig().audioPressure.load()){b.clip.scoreReason="audio_pressure";return false;}
  if(now-b.started>30000000LL){b.clip.scoreReason="deadline";return false;}
  if(now-b.lastYield>=1000){
   int64_t before=esp_timer_get_time();vTaskDelay(1);
   b.wait+=uint32_t(esp_timer_get_time()-before);b.lastYield=esp_timer_get_time();
  }
  return true;
 }
};
bool scoreOne(Clip& c) {
   if(c.state.load()!=OWNED || !c.lease.claim())return false;const int64_t started=esp_timer_get_time();
   c.probability=NAN;c.scoreReason="complete";
   if(c.test && c.seq==UINT32_MAX){
    float features[165];runOverlapTrial(c,features);
    c.scoreReason="overlap_test";c.valid=false;c.lease.score.store(RTClipLease::Done);return true;
   }
   ScoreBudget budget{c};float features[165];
   const bool featuresOK=ScoreBudget::check(&budget) &&
     RTFeatures::compute(c.pcm,c.n,workspace,features,nullptr,ScoreBudget::check,&budget);
   c.featureUs=uint32_t(esp_timer_get_time()-started);
   if(featuresOK && ScoreBudget::check(&budget)){
    if(c.test){for(int i=0;i<164;++i)if(fabsf(features[i])>1e-5f)c.valid=false;
      if(fabsf(features[164]-log1pf(float(RTFeatures::MAX_FRAMES)))>1e-5f)c.valid=false;}
    const int64_t modelStart=esp_timer_get_time();
    c.probability=RTModel::score(*model,features);
    c.modelUs=uint32_t(esp_timer_get_time()-modelStart);
   }else if(!strcmp(c.scoreReason,"complete"))c.scoreReason="invalid_features";
   c.valid=c.valid && featuresOK && std::isfinite(c.probability);
   c.threshold=model->threshold;c.us=uint32_t(esp_timer_get_time()-started);
   c.waitUs=budget.wait;c.chunkUs=budget.peakChunk;
   if(!c.valid)++scoreSkipped;else ++scoreValid;
   ++completed;c.lease.score.store(RTClipLease::Done);return true;
}
void worker(void*) {
 for(;;){bool worked=false;
  for(auto& c:clips)worked=scoreOne(c)||worked;
  vTaskDelay(pdMS_TO_TICKS(worked?1:20));
 }
}
