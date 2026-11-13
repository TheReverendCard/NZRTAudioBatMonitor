#pragma once
#include <stdint.h>
// No allocation, I/O or locks. Sampled by a separate task once per second.
namespace RtGuard {
enum Fault : uint32_t { OK=0, Reader=1, DSP=2, Windows=3, Reporter=4 };
struct Inputs { uint32_t run, read, dsp, windows, report; bool enabled, expectWindows; };
struct Progress {
 uint32_t value=0,since=0;
 void prime(uint32_t now,uint32_t v){value=v;since=now;}
 uint32_t age(uint32_t now,uint32_t v){
   if(v!=value)prime(now,v);
   return now-since; // rollover safe for these short durations
 }
};
struct Decision { Fault fault; bool restart; };
struct Policy {
 Progress rd,dp,win,rep;
 bool armed=false,spent=false;
 uint32_t run=0;
 Decision sample(uint32_t now,const Inputs& s){
   if(!s.enabled){armed=false;return {OK,false};}
   if(!armed||s.run!=run){
     armed=true;run=s.run;rd.prime(now,s.read);dp.prime(now,s.dsp);
     win.prime(now,s.windows);rep.prime(now,s.report);return {OK,false};
   }
   auto a=rd.age(now,s.read),b=dp.age(now,s.dsp),c=win.age(now,s.windows),d=rep.age(now,s.report);
   if(!s.expectWindows)win.prime(now,s.windows);
   Fault fault=a>=30000?Reader:b>=30000?DSP:s.expectWindows&&c>=30000?Windows:d>=180000?Reporter:OK;
   bool restart=fault!=OK&&!spent;
   if(restart)spent=true;
   return {fault,restart};
 }
};
// Retained record validated only on software restart. An independent power cycle
// rearms the one-restart allowance; no NVS/flash operations in the observer.
constexpr uint32_t MAGIC=0x52544731u;
struct Record {uint32_t magic,reason,inverse;};
inline bool valid(const Record& r){return r.magic==MAGIC && r.reason>=Reader &&
 r.reason<=Reporter && r.inverse==~r.reason;}
inline Record record(Fault f){return {MAGIC,uint32_t(f),~uint32_t(f)};}
}
