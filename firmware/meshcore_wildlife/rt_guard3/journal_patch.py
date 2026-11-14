def upgrade(s):
 s=s.replace('#include <SPIFFS.h>','#include <SPIFFS.h>\n#include "RTJournalPolicy.h"\n#include "GuardSignals.h"')
 s=s.replace('JOURNAL-4','JOURNAL-5')
 s=s.replace('uint32_t errors=0,','RTJournalPolicy circuit;\n  const char* lastReason="none";\n  uint32_t firstFailure=0,lastFailure=0,pressureDeferred=0;\n  size_t cachedBytes=0,expectedBytes=0,observedBytes=0,verifyOffset=0;\n  uint32_t expectedHash=0,observedHash=0;\n  uint32_t errors=0,')
 s=s.replace('Stats& s=stats();++s.errors;', 'Stats& s=stats();s.lastReason=why;s.lastFailure=millis();if(!s.errors)s.firstFailure=millis();s.circuit.failure(millis());++s.errors;',1)
 s=s.replace('const Stats& s=stats();\n  return s.nextRetry', 'Stats& s=stats();\n  return s.circuit.blocked(millis()) || (s.nextRetry')
 s=s.replace('(int32_t)(millis()-s.nextRetry)<0;','(int32_t)(millis()-s.nextRetry)<0);')
 s=s.replace('    if(inCooldown()) {++stats().deferred;return;}','    if(inCooldown()) {++stats().deferred;return;}\n    if(RtWatch::sig().audioPressure.load()){++stats().pressureDeferred;return;}')
 # A failure in tail inspection may trip the circuit in this constructor.
 s=s.replace('    if(tailBad) {\n      if(!isolateActive())return;', '    if(tailBad) {\n      stats().repairPending=true;\n      if(inCooldown() || !isolateActive())return;')
 s=s.replace('    if(!checkedSize(path(2),active)) {\n      if(!isolateActive())return;', '    if(!checkedSize(path(2),active)) {\n      stats().repairPending=true;\n      if(inCooldown() || !isolateActive())return;')
 s=s.replace('    ok=!bad && r && r.size()==start+count && r.seek(start);', '    stats().expectedBytes=start+count;stats().observedBytes=r?r.size():0;stats().verifyOffset=start;\n    stats().expectedHash=hash;\n    ok=!bad && r && r.size()==start+count && r.seek(start);')
 s=s.replace('    r.close();ok=ok && actual==hash;', '    stats().observedHash=actual;\n    r.close();ok=ok && actual==hash;')
 s=s.replace('++s.verified;s.lastOK=millis();', '++s.verified;s.cachedBytes=start+count;s.lastOK=millis();')
 s=s.replace('Stats& s=stats();s.readFault=true;++s.errors;', 'Stats& s=stats();s.readFault=true;fail(why);')
 s=s.replace('  size_t bytes=sizeOf(path(0))+sizeOf(path(1))+sizeOf(path(2))+sizeOf(pendingPath());', '  size_t bytes=stats().cachedBytes; // last verified active length, no diagnostic flash reads')
 s=s.replace(' bytes=%lu limit_segment=', ' active_verified_bytes=%lu limit_segment=')
 # RAM-only error telemetry works even when no journal can be opened.
 pos=s.index('inline bool dump()')
 s=s[:pos]+'''inline void ramStatus(char* out,size_t n,uint32_t session=0) {
  auto& s=stats();
  snprintf(out,n,"NZRT JOURNAL_RAM session=%08lx version=JOURNAL-5 errors=%lu reason=%s first_ms=%lu last_ms=%lu circuit=%u trips=%lu pressure_deferred=%lu expected_bytes=%lu observed_bytes=%lu offset=%lu expected_hash=%08lx observed_hash=%08lx",
    (unsigned long)session,(unsigned long)s.errors,s.lastReason,(unsigned long)s.firstFailure,(unsigned long)s.lastFailure,
    unsigned(s.circuit.blocked(millis())),(unsigned long)s.circuit.trips,(unsigned long)s.pressureDeferred,
    (unsigned long)s.expectedBytes,(unsigned long)s.observedBytes,(unsigned long)s.verifyOffset,
    (unsigned long)s.expectedHash,(unsigned long)s.observedHash);
}
inline uint32_t& diagnosticSent(){static uint32_t at=0;return at;}
inline uint32_t& diagnosticErrors(){static uint32_t n=0;return n;}
inline bool diagnosticDue(){return stats().errors && (stats().errors!=diagnosticErrors() || uint32_t(millis()-diagnosticSent())>=300000UL);}
inline void diagnosticAck(){diagnosticErrors()=stats().errors;diagnosticSent()=millis();}
''' +s[pos:]
 return s
