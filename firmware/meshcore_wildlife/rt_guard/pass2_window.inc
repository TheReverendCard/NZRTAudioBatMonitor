   const unsigned selected=cfg&3, shadow=(cfg>>2)&3;
   bool hits[3]={legacyHot,false,false},evaluated[3]={true,false,false};
   bool ranWork=false;
   const uint32_t started=passClock();
   // The primary has first use of the budget. Never start the comparison after
   // a costly primary. Kernels also check the shared deadline between small chunks.
   for(unsigned slot=0;slot<2;++slot){
     const unsigned id=slot?(shadow?shadow-1:0):selected;
     if(!id)continue;
     const bool blocked=queuePressure || optionalHoldSamples || cooldown[id] ||
                        (ranWork && deadline(started));
     if(blocked){
       if(cooldown[id])--cooldown[id];
       if(skips[id]<51)++skips[id];
       if(slot)RtWatch::bump(RtWatch::sig().held);
       continue;
     }
     if(skips[id]){
       if(id==1)for(auto& b:FirstPass::bands())b.z1=b.z2=0;
       if(skips[id]>50)clearShadow(id+1);
       skips[id]=0;
     }
     evaluated[id]=id==1 ? FirstPass::warmE>=5 : FirstPass::audible.load()->warm>=10;
     bool complete=true;
     hits[id]=id==1 ? FirstPass::evolved(pcmWindow,started,complete) : FirstPass::audible.load()->check(pcmWindow,started,complete);
     ranWork=true;
     if(!complete){evaluated[id]=false;skips[id]=1;}
     if(!complete || deadline(started)){cooldown[id]=slot?250:4;++overBudget;}
   }
   const bool selectedReady=evaluated[selected];
   const bool provisional=selected && !selectedReady;
   const bool assist=(cfg&16)!=0;
   const bool allowLegacy=!selected || provisional || assist;
   const bool hot=hits[selected] || (allowLegacy && legacyHot);
   const bool shadowHit=shadow && hits[shadow-1];
   if(selected){if(selectedReady)++newReady;else ++baseCoverage;}
   const unsigned source=(allowLegacy && legacyHot ? 1u : 0u) |
                         (selected && hits[selected] ? 1u<<selected : 0u);
   if(selected && hits[selected] && !legacyHot)++newOnly;
   if(selected && (source&1) && !hits[selected])++legacyRescue;
   ++passWindows;if(hot)++activeHot;if(shadowHit)++shadowHot;if(shadowHit&&!hot)++shadowOnly;
   const unsigned dt=uint32_t(passClock()-started);lastPassUs.store(dt);
   if(dt>maxPassUs.load())maxPassUs.store(dt);
