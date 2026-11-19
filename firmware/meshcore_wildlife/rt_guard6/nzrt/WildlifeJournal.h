#pragma once
// JOURNAL-6 fail-open patch to the SHA-matched installed JOURNAL-3 source.
// Main-loop only. Never call from the audio tasks or interrupt handlers.
#include <Arduino.h>
#include <esp_timer.h>
#include <SPIFFS.h>
#include "RTJournalPolicy.h"
#include "RTLogSpool.h"
#include <esp_heap_caps.h>
#include "GuardSignals.h"
#include <Stream.h>
namespace WildlifeJournal {
static constexpr size_t SEGMENT = 256UL*1024UL;
static constexpr size_t RESERVE = 384UL*1024UL;
static constexpr uint32_t RETRY_MS = 30000UL;
static constexpr const char* QUARANTINED = "/packet_log.bad";
inline const char* path(int i) { return i==0?"/packet_log.2":i==1?"/packet_log.1":"/packet_log"; }
struct Stats {
  RTJournalPolicy circuit;
  const char* lastReason="none";
  uint32_t firstFailure=0,lastFailure=0,pressureDeferred=0;
  size_t cachedBytes=0,expectedBytes=0,observedBytes=0,verifyOffset=0;
  uint32_t expectedHash=0,observedHash=0;
  uint32_t errors=0, verified=0, rotations=0, discarded=0, lastOK=0;
  uint32_t consecutive=0, nextRetry=0, deferred=0, quarantined=0;
  uint32_t activeDiscarded=0, skippedSources=0;
  size_t storageTotal=0,storageUsed=0;
  bool latched=false;uint32_t flashOps=0,protectedDeferrals=0;
  bool fault=false, readFault=false, repairPending=false;
};
inline Stats& stats() { static Stats s; return s; }
inline void fail(const char* why) {
  Stats& s=stats();s.latched=true;s.lastReason=why;s.lastFailure=millis();if(!s.errors)s.firstFailure=millis();s.circuit.failure(millis());++s.errors;++s.consecutive;s.fault=true;
  s.nextRetry=millis()+RETRY_MS;
  if(s.consecutive<=3 || (s.consecutive%16)==0)
    Serial.printf("NZRT JOURNAL ERROR reason=%s errors=%lu consecutive=%lu\n",
                  why,(unsigned long)s.errors,(unsigned long)s.consecutive);
}
// A failed open must not be interpreted as an empty journal.
inline bool flashSafe(){return RtWatch::sig().flashIdle.load();}
inline bool saneSize(size_t n){return n<=SEGMENT+65536UL && stats().storageTotal && n<=stats().storageTotal;}
inline bool checkedSize(const char* p, size_t& n) {
  n=0;if(!SPIFFS.exists(p))return true;
  File f=SPIFFS.open(p,FILE_READ);
  if(!f){fail("size_open");Serial.printf("NZRT JOURNAL DETAIL file=%s\n",p);return false;}
  n=f.size();f.close();if(!saneSize(n)){stats().observedBytes=n;fail("invalid_size");return false;}return true;
}
inline size_t sizeOf(const char* p) {size_t n=0;checkedSize(p,n);return n;}
inline const char* pendingPath(){return "/packet_log.pending";}
inline bool inCooldown() {
  Stats& s=stats();
  return s.latched || s.circuit.blocked(millis()) || (s.nextRetry && (int32_t)(millis()-s.nextRetry)<0);
}
// Damaged active journals are retained for explicit idle inspection. No automatic repair.
// Pending is the old active file. No new active file is opened until this
// transaction completes. Each rename is checked; retries preserve its stage.
inline bool finishRotation() {
  if(!SPIFFS.exists(pendingPath()))return true;
  if(SPIFFS.exists(path(2))) {
    // Staged old log + a newer active log after interruption: keep the new
    // log, discard only the redundant staged journal, and continue.
    if(!SPIFFS.remove(pendingPath())) {fail("rotation_pending_conflict");return false;}
    ++stats().discarded;
    Serial.println("NZRT JOURNAL RETENTION stale_pending_discarded=1");
    return true;
  }
  if(SPIFFS.exists(path(1))) {
    size_t lost=0;if(!checkedSize(path(0),lost))return false;
    if(SPIFFS.exists(path(0)) && !SPIFFS.remove(path(0))){fail("remove_oldest");return false;}
    if(lost)++stats().discarded;
    if(!SPIFFS.rename(path(1),path(0))){fail("rotate_previous");return false;}
  }
  if(!SPIFFS.rename(pendingPath(),path(1))){fail("rotate_pending");return false;}
  ++stats().rotations;return true;
}
inline bool rotate() {
  if(!finishRotation())return false;
  if(!SPIFFS.exists(path(2)))return true;
  if(!SPIFFS.rename(path(2),pendingPath())){fail("rotate_stage");return false;}
  return finishRotation();
}
// Writer operations run on the main loop. Nesting can occur when the
// constructor writes a segment header. Count that time only once.
struct WriteTiming { uint32_t total=0,peak=0,depth=0;bool enabled=false; };
inline WriteTiming& writeTiming(){static WriteTiming sample;return sample;}
inline void startWriteTiming(){auto& t=writeTiming();t=WriteTiming();t.enabled=true;}
inline WriteTiming stopWriteTiming(){auto& t=writeTiming();t.enabled=false;return t;}
struct MeasureWrite {
  bool active;
  uint32_t since=0;
  MeasureWrite():active(writeTiming().enabled){
    if(active && writeTiming().depth++==0)since=esp_timer_get_time();
  }
  ~MeasureWrite(){
    if(!active)return;
    auto& t=writeTiming();
    if(--t.depth==0){
      uint32_t elapsed=uint32_t(esp_timer_get_time())-since;
      t.total+=elapsed;if(elapsed>t.peak)t.peak=elapsed;
    }
  }
};
class FlashWriter : public Print {
  File f; size_t start=0,count=0; uint32_t hash=2166136261UL; bool bad=false,done=false,ok=false;
public:
  FlashWriter() {
    MeasureWrite measure;
    if(!flashSafe()){++stats().protectedDeferrals;return;}
    if(inCooldown()) {++stats().deferred;return;}
    if(RtWatch::sig().audioPressure.load()){++stats().pressureDeferred;return;}
    if(stats().repairPending){fail("repair_requires_manual_idle");return;}
    size_t total=SPIFFS.totalBytes(), used=SPIFFS.usedBytes();
    stats().storageTotal=total;stats().storageUsed=used;
    if(!total || used>total) {fail("filesystem_unavailable");return;}
    ++stats().flashOps;
    if(!finishRotation())return;
    size_t active=0;
    if(!checkedSize(path(2),active)) {
      stats().repairPending=true;
      return;
    }
    if(active>=SEGMENT){if(!rotate())return;active=0;}
    // Reserve flash headroom for SPIFFS GC. Reclaim only journal archives.
    for(int i=0;i<2 && (SPIFFS.usedBytes()>total || total-SPIFFS.usedBytes()<RESERVE);++i) {
      if(SPIFFS.exists(path(i))) {
        size_t lost=0;if(!checkedSize(path(i),lost))return;
        if(!SPIFFS.remove(path(i))) {fail("reserve_reclaim");return;}
        ++stats().discarded;
        Serial.printf("NZRT JOURNAL RETENTION reserve_discarded_bytes=%lu\n",(unsigned long)lost);
      }
    }
    used=SPIFFS.usedBytes();
    if((used>total || total-used<RESERVE) && SPIFFS.exists(QUARANTINED)) {
      if(!SPIFFS.remove(QUARANTINED)) {fail("low_space_quarantine");return;}
      ++stats().discarded;
      used=SPIFFS.usedBytes();
    }
    if(used>total || total-used<RESERVE) {fail("low_space");return;}
    // If the old tail is unreadable, isolate this journal and proceed with
    // a new active segment. Do not retry the same damaged byte forever.
    bool newline=false, tailBad=false;
    File tail;bool existed=SPIFFS.exists(path(2));
    if(existed)tail=SPIFFS.open(path(2),FILE_READ);
    if(existed && !tail) {fail("tail_open");tailBad=true;}
    if(tail && active) {
      if(!tail.seek(active-1)){fail("tail_seek");tailBad=true;}
      else {
        int c=tail.read();
        if(c<0){fail("tail_read");tailBad=true;}
        else newline=c!='\n';
      }
    }
    tail.close();
    if(tailBad) {
      stats().repairPending=true;
      return;
    }
    f=SPIFFS.open(path(2),FILE_APPEND);
    if(!f) {fail("open_append");return;}
    // Arduino-ESP32 2.0.17 leaves cached stat uninitialised on a NEW file.
    // Never call size() on a new append handle. Use the validated pre-open size.
    start=active;
    if(newline) write((uint8_t)'\n');
    if(start==0) printf("NZRT JOURNAL segment_start=1 uptime_ms=%lu retention_discards_boot=%lu errors_boot=%lu\n",(unsigned long)millis(),(unsigned long)stats().discarded,(unsigned long)stats().errors);
  }
  FlashWriter(const FlashWriter&)=delete; FlashWriter& operator=(const FlashWriter&)=delete;
  operator bool() const {return (bool)f && !bad;}
  using Print::write;
  size_t write(uint8_t c) override {return write(&c,1);}
  size_t write(const uint8_t* p,size_t n) override {
    MeasureWrite measure;
    if(!f || bad || done)return 0;
    // Maximum candidate batch is 64 x <1024 bytes.
    if(n>65536UL-count || start>SEGMENT+65536UL-count-n) {bad=true;fail("batch_limit");return 0;}
    size_t got=f.write(p,n);
    for(size_t i=0;i<got;++i)hash=(hash^p[i])*16777619UL;
    count+=got;
    if(got!=n) {bad=true;fail("short_write");}
    return got;
  }
  bool close() {
    if(done)return ok;
    MeasureWrite measure;
    done=true;
    if(!f)return false;
    f.flush();f.close();
    File r=SPIFFS.open(path(2),FILE_READ);
    stats().expectedBytes=start+count;stats().observedBytes=r?r.size():0;stats().verifyOffset=start;
    stats().expectedHash=hash;
    ok=!bad && r && saneSize(stats().observedBytes) && stats().observedBytes==start+count && r.seek(start);
    uint8_t b[512];size_t left=count;uint32_t actual=2166136261UL;
    while(ok && left) {
      size_t want=left>sizeof(b)?sizeof(b):left,got=r.read(b,want);
      if(got!=want){ok=false;break;}
      for(size_t i=0;i<got;++i)actual=(actual^b[i])*16777619UL;
      left-=got;
    }
    stats().observedHash=actual;
    r.close();ok=ok && actual==hash;
    if(!ok){stats().repairPending=true;fail("readback");}
    else {
      Stats& s=stats();
      if(s.fault)Serial.println("NZRT JOURNAL RECOVERY verified_new_write=1");
      ++s.verified;s.cachedBytes=start+count;s.lastOK=millis();s.fault=false;s.consecutive=0;s.nextRetry=0;
    }
    return ok;
  }
  ~FlashWriter(){close();}
};
// 1 MiB PSRAM spool plus one 64 KiB (+128 byte header) shared transaction/HTTP staging buffer.
// All users are the main loop. No flash calls occur in Writer, even at boot.
inline RTLogSpool::Queue& spool(){static RTLogSpool::Queue q;return q;}
struct RamBuffers {uint8_t* stage=nullptr;bool busy=false,attempted=false;};
inline RamBuffers& ram(){static RamBuffers r;return r;}
inline bool beginRam(){
 auto& r=ram();if(r.attempted)return r.stage && spool().availableCapacity();r.attempted=true;
 uint8_t* data=(uint8_t*)heap_caps_malloc(1024UL*1024UL,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
 r.stage=(uint8_t*)heap_caps_malloc(65536UL+128,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
 if(!data||!r.stage){free(data);free(r.stage);r.stage=nullptr;Serial.println("NZRT JOURNAL_RAM unavailable=allocation no_flash_fallback=1");return false;}
 return spool().init(data,1024UL*1024UL);
}
class Writer: public Print {
 size_t count=0;bool owned=false,bad=false,done=false,ok=false;
public:
 Writer(){MeasureWrite measure;if(beginRam()&&!ram().busy){ram().busy=true;owned=true;}else ++spool().rejected;}
 Writer(const Writer&)=delete;Writer& operator=(const Writer&)=delete;
 operator bool()const{return owned&&!bad&&!done;}
 using Print::write;
 size_t write(uint8_t c)override{return write(&c,1);}
 size_t write(const uint8_t* p,size_t n)override{
  MeasureWrite measure;
  if(!owned||bad||done)return 0;
  if(n>65536UL-count){bad=true;return 0;}memcpy(ram().stage+count,p,n);count+=n;return n;
 }
 bool close(){
  if(done)return ok;MeasureWrite measure;done=true;if(!owned)return false;
  ok=!bad && count && spool().push(ram().stage,count);ram().busy=false;owned=false;return ok;
 }
 ~Writer(){close();}
};
inline void service(){
 // A write fault latches for this boot. No timed repair, quarantine, or retry loop.
 if(!flashSafe()||inCooldown()||!beginRam()||ram().busy||spool().empty())return;
 ram().busy=true;uint64_t token=0;size_t n=spool().oldest(ram().stage,65536,token);
 if(n){FlashWriter f;if(f && f.write(ram().stage,n)==n && f.close())spool().saved(token);}
 ram().busy=false;
}
inline bool hasPendingUpload(){return spool().pending();}
inline size_t prepareUpload(uint8_t*& data,uint64_t& token){
 data=nullptr;if(!beginRam()||ram().busy)return 0;ram().busy=true;data=ram().stage+128;
 size_t n=spool().upload(data,65536,token);if(!n){ram().busy=false;data=nullptr;}return n;
}
inline void finishUpload(bool verified,uint64_t token){if(verified)spool().confirm(token);ram().busy=false;}

// Complete-line concatenation of oldest, previous and active. No temporary file.
// Caller must keep all writers on the same main loop while streaming.
class Reader : public Stream {
  File f;size_t lengths[4]={0,0,0,0},remaining=0,total=0;int index=-1;bool valid=true;
  const char* source(int i) const {return i<2?path(i):i==2?pendingPath():path(2);}
  void readError(const char* why,int i,size_t offset,bool fatal=true) {
    Stats& s=stats();s.readFault=true;fail(why);
    if(fatal)valid=false;
    ++s.skippedSources;
    Serial.printf("NZRT JOURNAL READ_ERROR file=%s offset=%lu reason=%s skip=%u\n",
                  source(i),(unsigned long)offset,why,!fatal);
  }
  bool advance() {
    if(!valid || index>=4)return false;
    while(!remaining && ++index<4) {
      f.close();remaining=lengths[index];
      if(remaining){f=SPIFFS.open(source(index),FILE_READ);if(!f){readError("reader_open",index,0);remaining=0;return false;}}
    }
    return remaining>0;
  }
public:
  Reader() {
    if(!flashSafe()){valid=false;++stats().protectedDeferrals;return;}
    stats().storageTotal=SPIFFS.totalBytes();
    // Read each candidate segment end-to-end before allowing export.
    // A single corrupt legacy segment is skipped; intact newer records
    // remain deliverable. This preflight occurs only on explicit export.
    for(int i=0;i<4;++i) {
      if(!SPIFFS.exists(source(i)))continue;
      File r=SPIFFS.open(source(i),FILE_READ);
      if(!r){readError("reader_scan_open",i,0,false);continue;}
      size_t pos=0,lastNewline=0,expected=r.size();uint8_t buf[512];
      bool readable=true;
      if(!stats().storageTotal || expected>stats().storageTotal){r.close();readError("reader_invalid_size",i,0,false);continue;}
      while(pos<expected) {
        size_t want=expected-pos>sizeof(buf)?sizeof(buf):expected-pos;
        size_t got=r.read(buf,want);
        if(got!=want){readError("reader_scan_read",i,pos,false);readable=false;break;}
        for(size_t j=0;j<got;++j)if(buf[j]=='\n')lastNewline=pos+j+1;
        pos+=got;
      }
      r.close();
      if(!readable)continue;
      lengths[i]=lastNewline;
      total+=lastNewline;
    }
    rewind();
  }
  bool good() const {return valid;}
  size_t size() const {return total;}
  void rewind(){f.close();index=-1;remaining=0;if(valid)advance();}
  int available() override {if(!valid)return 0;if(!remaining)advance();return (int)remaining;}
  int read() override {
    if(!available())return -1;
    int c=f.read();
    if(c<0){readError("reader_read",index,lengths[index]-remaining);remaining=0;return -1;}
    --remaining;return c;
  }
  size_t readBytes(char* out,size_t want) override {
    size_t got=0;
    while(got<want && available()) {
      size_t take=want-got<remaining?want-got:remaining;
      size_t n=f.read((uint8_t*)out+got,take);
      got+=n;remaining-=n;
      if(n!=take){readError("reader_short_read",index,lengths[index]-remaining);remaining=0;break;}
    }
    return got;
  }
  int peek() override {return available()?f.peek():-1;}
  void flush() override {}
  size_t write(uint8_t) override {return 0;}
  void close(){f.close();remaining=0;index=4;}
};
inline void status(Print& out=Serial) {
  out.printf("NZRT JOURNAL_QUEUE capacity=1048576 ram_bytes=%lu unconfirmed_lost=%lu volatile=1 flash_latched=%u\n",(unsigned long)spool().used(),(unsigned long)spool().unconfirmedLost,unsigned(stats().latched));
  size_t bytes=stats().cachedBytes; // last verified active length, no diagnostic flash reads
  Stats& s=stats();
  out.printf("NZRT JOURNAL version=JOURNAL-6 fault=%u errors=%lu verified=%lu rotations=%lu retention_discards=%lu last_ok_uptime_ms=%lu active_verified_bytes=%lu limit_segment=%lu reserve=%lu read_fault=%u quarantined=%lu active_discarded=%lu export_skips=%lu retry_deferred=%lu cooldown=%u counters=since_boot\n",
    (s.fault||s.readFault),(unsigned long)s.errors,(unsigned long)s.verified,
    (unsigned long)s.rotations,(unsigned long)s.discarded,(unsigned long)s.lastOK,
    (unsigned long)bytes,(unsigned long)SEGMENT,(unsigned long)RESERVE,
    (unsigned)s.readFault,(unsigned long)s.quarantined,(unsigned long)s.activeDiscarded,
    (unsigned long)s.skippedSources,(unsigned long)s.deferred,(unsigned)inCooldown());
}
inline void ramStatus(char* out,size_t n,uint32_t session=0) {
 auto& s=stats();auto& q=spool();
 snprintf(out,n,"NZRT JOURNAL_RAM version=JOURNAL-6 session=%08lx errors=%lu reason=%s first_ms=%lu last_ms=%lu circuit=%u latched=%u flash_idle=%u flash_ops=%lu expected_bytes=%lu observed_bytes=%lu offset=%lu ram_ready=%u ram_bytes=%lu ram_evicted=%lu unconfirmed_lost=%lu rejected=%lu ram_ack=%lu flash_saved=%lu volatile=1",
 (unsigned long)session,(unsigned long)s.errors,s.lastReason,(unsigned long)s.firstFailure,(unsigned long)s.lastFailure,unsigned(inCooldown()),unsigned(s.latched),unsigned(flashSafe()),(unsigned long)s.flashOps,
 (unsigned long)s.expectedBytes,(unsigned long)s.observedBytes,(unsigned long)s.verifyOffset,unsigned(q.availableCapacity()!=0),(unsigned long)q.used(),(unsigned long)q.evicted,(unsigned long)q.unconfirmedLost,(unsigned long)q.rejected,(unsigned long)q.acked,(unsigned long)q.flashSaved);
}
inline uint32_t& diagnosticSent(){static uint32_t at=0;return at;}
inline uint32_t& diagnosticErrors(){static uint32_t n=0;return n;}
inline bool diagnosticDue(){return stats().errors && (stats().errors!=diagnosticErrors() || uint32_t(millis()-diagnosticSent())>=300000UL);}
inline void diagnosticAck(){diagnosticErrors()=stats().errors;diagnosticSent()=millis();}
inline bool dump() {
  if(!flashSafe()){Serial.println("NZRT JOURNAL dump_deferred=1 use_wifi_ram_upload=1");return false;}
  Reader r;char buf[512];
  while(r.available()){size_t n=r.readBytes(buf,sizeof(buf));if(n)Serial.write((const uint8_t*)buf,n);if(!r.good() || !n)break;}
  if(!r.good())fail("dump_read");
  return r.good();
}
inline bool erase() {
  if(!flashSafe()){Serial.println("NZRT JOURNAL erase_deferred=1 requires_capture_stopped=1");return false;}
  bool ok=true;
  for(int i=0;i<3;++i)if(SPIFFS.exists(path(i)) && !SPIFFS.remove(path(i)))ok=false;
  if(SPIFFS.exists(pendingPath()) && !SPIFFS.remove(pendingPath()))ok=false;
  if(SPIFFS.exists(QUARANTINED) && !SPIFFS.remove(QUARANTINED))ok=false;
  if(!ok)fail("erase");
  else {spool().clear();stats().circuit=RTJournalPolicy();stats().latched=false;stats().fault=false;stats().readFault=false;stats().consecutive=0;stats().nextRetry=0;stats().repairPending=false;}
  return ok;
}
inline void test() {Writer w;if(w){w.printf("NZRT JOURNAL_TEST uptime_ms=%lu\n",(unsigned long)millis());bool ok=w.close();Serial.printf("NZRT JOURNAL_TEST queued_ram=%u durable=0\n",unsigned(ok));}status();}
}

