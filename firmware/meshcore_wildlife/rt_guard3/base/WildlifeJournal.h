#pragma once
// JOURNAL-4 fail-open patch to the SHA-matched installed JOURNAL-3 source.
// Main-loop only. Never call from the audio tasks or interrupt handlers.
#include <Arduino.h>
#include <esp_timer.h>
#include <SPIFFS.h>
#include <Stream.h>
namespace WildlifeJournal {
static constexpr size_t SEGMENT = 256UL*1024UL;
static constexpr size_t RESERVE = 384UL*1024UL;
static constexpr uint32_t RETRY_MS = 30000UL;
static constexpr const char* QUARANTINED = "/packet_log.bad";
inline const char* path(int i) { return i==0?"/packet_log.2":i==1?"/packet_log.1":"/packet_log"; }
struct Stats {
  uint32_t errors=0, verified=0, rotations=0, discarded=0, lastOK=0;
  uint32_t consecutive=0, nextRetry=0, deferred=0, quarantined=0;
  uint32_t activeDiscarded=0, skippedSources=0;
  bool fault=false, readFault=false, repairPending=false;
};
inline Stats& stats() { static Stats s; return s; }
inline void fail(const char* why) {
  Stats& s=stats();++s.errors;++s.consecutive;s.fault=true;
  s.nextRetry=millis()+RETRY_MS;
  if(s.consecutive<=3 || (s.consecutive%16)==0)
    Serial.printf("NZRT JOURNAL ERROR reason=%s errors=%lu consecutive=%lu\n",
                  why,(unsigned long)s.errors,(unsigned long)s.consecutive);
}
// A failed open must not be interpreted as an empty journal.
inline bool checkedSize(const char* p, size_t& n) {
  n=0;if(!SPIFFS.exists(p))return true;
  File f=SPIFFS.open(p,FILE_READ);
  if(!f){fail("size_open");Serial.printf("NZRT JOURNAL DETAIL file=%s\n",p);return false;}
  n=f.size();f.close();return true;
}
inline size_t sizeOf(const char* p) {size_t n=0;checkedSize(p,n);return n;}
inline const char* pendingPath(){return "/packet_log.pending";}
inline bool inCooldown() {
  const Stats& s=stats();
  return s.nextRetry && (int32_t)(millis()-s.nextRetry)<0;
}
// Reclaim only files owned by the journal, never MeshCore identities,
// credentials, RT models, or the entire SPIFFS filesystem.
inline bool isolateActive() {
  if(!SPIFFS.exists(path(2))) {stats().repairPending=false;return true;}
  if(SPIFFS.exists(QUARANTINED)) {
    if(!SPIFFS.remove(QUARANTINED)) {fail("quarantine_reclaim");return false;}
    ++stats().discarded;
  }
  if(SPIFFS.rename(path(2),QUARANTINED)) {
    ++stats().quarantined;
    stats().repairPending=false;
    Serial.println("NZRT JOURNAL RECOVERY active_quarantined=1");
    return true;
  }
  // The owner has retained a verified full-flash backup and explicitly
  // prioritises newer detection over endlessly preserving an unreadable log.
  // Removal is restricted to the *active journal path*.
  if(SPIFFS.remove(path(2))) {
    ++stats().activeDiscarded;
    ++stats().discarded;
    stats().repairPending=false;
    Serial.println("NZRT JOURNAL RECOVERY active_discarded=1 rename_failed=1");
    return true;
  }
  fail("isolate_active_failed");
  return false;
}
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
class Writer : public Print {
  File f; size_t start=0,count=0; uint32_t hash=2166136261UL; bool bad=false,done=false,ok=false;
public:
  Writer() {
    MeasureWrite measure;
    if(inCooldown()) {++stats().deferred;return;}
    if(stats().repairPending && !isolateActive())return;
    size_t total=SPIFFS.totalBytes(), used=SPIFFS.usedBytes();
    if(!total) {fail("filesystem_unavailable");return;}
    if(!finishRotation())return;
    size_t active=0;
    if(!checkedSize(path(2),active)) {
      if(!isolateActive())return;
      active=0;
    }
    if(active>=SEGMENT && !rotate())return;
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
    if(tail && tail.size()) {
      if(!tail.seek(tail.size()-1)){fail("tail_seek");tailBad=true;}
      else {
        int c=tail.read();
        if(c<0){fail("tail_read");tailBad=true;}
        else newline=c!='\n';
      }
    }
    tail.close();
    if(tailBad) {
      if(!isolateActive())return;
      newline=false;
    }
    f=SPIFFS.open(path(2),FILE_APPEND);
    if(!f) {fail("open_append");return;}
    start=f.size();
    if(newline) write((uint8_t)'\n');
    if(start==0) printf("NZRT JOURNAL segment_start=1 uptime_ms=%lu retention_discards_boot=%lu errors_boot=%lu\n",(unsigned long)millis(),(unsigned long)stats().discarded,(unsigned long)stats().errors);
  }
  Writer(const Writer&)=delete; Writer& operator=(const Writer&)=delete;
  operator bool() const {return (bool)f && !bad;}
  using Print::write;
  size_t write(uint8_t c) override {return write(&c,1);}
  size_t write(const uint8_t* p,size_t n) override {
    MeasureWrite measure;
    if(!f || bad || done)return 0;
    // Maximum candidate batch is 64 x <1024 bytes.
    if(count+n>65536UL) {bad=true;fail("batch_limit");return 0;}
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
    ok=!bad && r && r.size()==start+count && r.seek(start);
    uint8_t b[512];size_t left=count;uint32_t actual=2166136261UL;
    while(ok && left) {
      size_t want=left>sizeof(b)?sizeof(b):left,got=r.read(b,want);
      if(got!=want){ok=false;break;}
      for(size_t i=0;i<got;++i)actual=(actual^b[i])*16777619UL;
      left-=got;
    }
    r.close();ok=ok && actual==hash;
    if(!ok){stats().repairPending=true;fail("readback");}
    else {
      Stats& s=stats();
      if(s.fault)Serial.println("NZRT JOURNAL RECOVERY verified_new_write=1");
      ++s.verified;s.lastOK=millis();s.fault=false;s.consecutive=0;s.nextRetry=0;
    }
    return ok;
  }
  ~Writer(){close();}
};
// Complete-line concatenation of oldest, previous and active. No temporary file.
// Caller must keep all writers on the same main loop while streaming.
class Reader : public Stream {
  File f;size_t lengths[4]={0,0,0,0},remaining=0,total=0;int index=-1;bool valid=true;
  const char* source(int i) const {return i<2?path(i):i==2?pendingPath():path(2);}
  void readError(const char* why,int i,size_t offset,bool fatal=true) {
    Stats& s=stats();s.readFault=true;++s.errors;
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
    // Read each candidate segment end-to-end before allowing export.
    // A single corrupt legacy segment is skipped; intact newer records
    // remain deliverable. This preflight occurs only on explicit export.
    for(int i=0;i<4;++i) {
      if(!SPIFFS.exists(source(i)))continue;
      File r=SPIFFS.open(source(i),FILE_READ);
      if(!r){readError("reader_scan_open",i,0,false);continue;}
      size_t pos=0,lastNewline=0,expected=r.size();uint8_t buf[512];
      bool readable=true;
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
  size_t bytes=sizeOf(path(0))+sizeOf(path(1))+sizeOf(path(2))+sizeOf(pendingPath());
  Stats& s=stats();
  out.printf("NZRT JOURNAL version=JOURNAL-4 fault=%u errors=%lu verified=%lu rotations=%lu retention_discards=%lu last_ok_uptime_ms=%lu bytes=%lu limit_segment=%lu reserve=%lu read_fault=%u quarantined=%lu active_discarded=%lu export_skips=%lu retry_deferred=%lu cooldown=%u counters=since_boot\n",
    (s.fault||s.readFault),(unsigned long)s.errors,(unsigned long)s.verified,
    (unsigned long)s.rotations,(unsigned long)s.discarded,(unsigned long)s.lastOK,
    (unsigned long)bytes,(unsigned long)SEGMENT,(unsigned long)RESERVE,
    (unsigned)s.readFault,(unsigned long)s.quarantined,(unsigned long)s.activeDiscarded,
    (unsigned long)s.skippedSources,(unsigned long)s.deferred,(unsigned)inCooldown());
}
inline bool dump() {
  Reader r;char buf[512];
  while(r.available()){size_t n=r.readBytes(buf,sizeof(buf));if(n)Serial.write((const uint8_t*)buf,n);if(!r.good() || !n)break;}
  if(!r.good())fail("dump_read");
  return r.good();
}
inline bool erase() {
  bool ok=true;
  for(int i=0;i<3;++i)if(SPIFFS.exists(path(i)) && !SPIFFS.remove(path(i)))ok=false;
  if(SPIFFS.exists(pendingPath()) && !SPIFFS.remove(pendingPath()))ok=false;
  if(SPIFFS.exists(QUARANTINED) && !SPIFFS.remove(QUARANTINED))ok=false;
  if(!ok)fail("erase");
  else {stats().fault=false;stats().readFault=false;stats().consecutive=0;stats().nextRetry=0;stats().repairPending=false;}
  return ok;
}
inline void test() {Writer w;if(w){w.printf("NZRT JOURNAL_TEST uptime_ms=%lu\n",(unsigned long)millis());bool ok=w.close();Serial.printf("NZRT JOURNAL_TEST result=%s\n",ok?"PASS":"FAIL");}status();}
}

