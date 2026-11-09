#pragma once
// FAIL-OPEN JOURNAL-4 PROTOTYPE, based on recovered JOURNAL-2.
 // NOT a verified match to owner-installed JOURNAL-3.
 // Main-loop only. Never call from audio tasks or interrupt handlers.
#include <Arduino.h>
#include <SPIFFS.h>
#include <Stream.h>
namespace WildlifeJournal {
static constexpr size_t SEGMENT = 256UL*1024UL;
static constexpr size_t RESERVE = 384UL*1024UL;
static constexpr const char* QUARANTINE = "/packet_log.bad";
static constexpr uint32_t RETRY_COOLDOWN_MS = 60000UL;
inline const char* path(int i) { return i==0?"/packet_log.2":i==1?"/packet_log.1":"/packet_log"; }
struct Stats {
  uint32_t errors=0, verified=0, rotations=0, discarded=0, lastOK=0;
  uint32_t consecutive=0, retryAfter=0, deferred=0, quarantines=0, skippedSegments=0;
  bool fault=false;
};
inline Stats& stats() { static Stats s; return s; }
inline void fail(const char* why) {
  Stats& s=stats(); ++s.errors; ++s.consecutive; s.fault=true;
  if(s.consecutive>=3) s.retryAfter=millis()+RETRY_COOLDOWN_MS;
  // Avoid flooding the serial link and starving main-loop housekeeping.
  if(s.consecutive<=3 || (s.consecutive%16)==0)
    Serial.printf("NZRT JOURNAL ERROR reason=%s errors=%lu consecutive=%lu\n",
        why,(unsigned long)s.errors,(unsigned long)s.consecutive);
}
inline bool coolingDown() {
  Stats& s=stats();
  if(s.retryAfter && (int32_t)(millis()-s.retryAfter)<0) return true;
  return false;
}
inline size_t sizeOf(const char* p) { if(!SPIFFS.exists(p))return 0; File f=SPIFFS.open(p,FILE_READ);size_t n=f?f.size():0;f.close();return n; }
inline bool rotate() {
  // Oldest-first renames: a reset between steps leaves readable segments.
  size_t lost=sizeOf(path(0));
  if(SPIFFS.exists(path(0)) && !SPIFFS.remove(path(0))) {fail("remove_oldest");return false;}
  if(lost) {++stats().discarded;Serial.printf("NZRT JOURNAL RETENTION oldest_bytes_discarded=%lu\n",(unsigned long)lost);}
  if(SPIFFS.exists(path(1)) && !SPIFFS.rename(path(1),path(0))) {fail("rotate_previous");return false;}
  if(SPIFFS.exists(path(2)) && !SPIFFS.rename(path(2),path(1))) {fail("rotate_active");return false;}
  ++stats().rotations;return true;
}
// Quarantine a single unreadable *journal file*, not the SPIFFS partition.
 // MeshCore identity, Wi-Fi settings and models are never erased here.
 // SPIFFS rename is metadata-only: the old data remains until space is needed.
inline bool quarantineActive() {
  if(!SPIFFS.exists(path(2)))return true;
  if(SPIFFS.exists(QUARANTINE) && !SPIFFS.remove(QUARANTINE)) {
    fail("quarantine_remove_old"); return false;
  }
  if(!SPIFFS.rename(path(2),QUARANTINE)) {
    fail("quarantine_rename"); return false;
  }
  ++stats().quarantines;
  Serial.printf("NZRT JOURNAL RECOVERY isolated=/packet_log.bad quarantines=%lu\n",
      (unsigned long)stats().quarantines);
  return true;
}
class Writer : public Print {
  File f; size_t start=0,count=0; uint32_t hash=2166136261UL; bool bad=false,done=false,ok=false;
public:
  Writer() {
    // Failed flash access must not be retried on every candidate/alive tick.
    if(coolingDown()) {++stats().deferred;return;}
    size_t total=SPIFFS.totalBytes(), used=SPIFFS.usedBytes();
    if(!total) {fail("filesystem_unavailable");return;}
    if(sizeOf(path(2))>=SEGMENT && !rotate()) return;
    // Reserve flash headroom for SPIFFS GC. Reclaim only journal archives.
    for(int i=0;i<2 && total-SPIFFS.usedBytes()<RESERVE;++i) {
      if(SPIFFS.exists(path(i))) {
        size_t lost=sizeOf(path(i));
        if(!SPIFFS.remove(path(i))) {fail("reserve_reclaim");return;}
        ++stats().discarded;
        Serial.printf("NZRT JOURNAL RETENTION reserve_discarded_bytes=%lu\n",(unsigned long)lost);
      }
    }
    // A quarantined log is expendable when SPIFFS needs garbage-collection space.
    used=SPIFFS.usedBytes();
    if(total>=used && total-used<RESERVE && SPIFFS.exists(QUARANTINE)) {
      if(!SPIFFS.remove(QUARANTINE)) {fail("quarantine_reclaim");return;}
      ++stats().discarded; used=SPIFFS.usedBytes();
    }
    if(used>total || total-used<RESERVE) {fail("low_space");return;}
    // A stale/corrupt last byte must not poison every subsequent append.
    bool newline=false, tailBad=false;
    bool exists=SPIFFS.exists(path(2));
    File tail;
    if(exists) tail=SPIFFS.open(path(2),FILE_READ);
    if(exists && !tail) tailBad=true;
    if(tail && tail.size()) {
      if(!tail.seek(tail.size()-1)) tailBad=true;
      else {
        int finalByte=tail.read();
        if(finalByte<0) tailBad=true;
        else newline=finalByte!='\n';
      }
    }
    tail.close();
    if(tailBad) {
      fail("tail_read");
      if(!quarantineActive())return;
      newline=false; // new active file begins at a clean line boundary
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
    if(!ok)fail("readback");
    else {
      Stats& s=stats();++s.verified;s.lastOK=millis();
      if(s.fault) Serial.println("NZRT JOURNAL RECOVERY write_verified=1");
      s.fault=false;s.consecutive=0;s.retryAfter=0;
    }
    return ok;
  }
  ~Writer(){close();}
};
// Complete-line concatenation of oldest, previous and active. No temporary file.
// Caller must keep all writers on the same main loop while streaming.
class Reader : public Stream {
  File f;size_t lengths[3]={0,0,0},remaining=0,total=0;int index=-1;bool valid=true;
  bool advance() {
    while(!remaining && ++index<3) {
      f.close();remaining=lengths[index];
      if(remaining){f=SPIFFS.open(path(index),FILE_READ);if(!f){valid=false;remaining=0;return false;}}
    }
    return remaining>0;
  }
public:
  Reader() {
    // Preflight every segment when explicitly exporting; this runs only in
    // the main-loop upload/serial path, never in the audio capture task.
    // Unreadable archives are omitted so yesterday's damaged segment
    // cannot prevent today's clean data from being exported.
    for(int i=0;i<3;++i) {
      if(!SPIFFS.exists(path(i)))continue;
      File r=SPIFFS.open(path(i),FILE_READ);
      if(!r) {
        ++stats().skippedSegments;
        Serial.printf("NZRT JOURNAL EXPORT_SKIP segment=%d open_failed=1\n",i);
        continue;
      }
      uint8_t buf[512];size_t pos=0,lastNewline=0,expected=r.size();
      bool readable=true;
      while(pos<expected) {
        size_t want=expected-pos>sizeof(buf)?sizeof(buf):expected-pos;
        size_t n=r.read(buf,want);
        if(n!=want){readable=false;break;}
        for(size_t j=0;j<n;++j)if(buf[j]=='\n')lastNewline=pos+j+1;
        pos+=n;
      }
      r.close();
      if(!readable) {
        ++stats().skippedSegments;
        Serial.printf("NZRT JOURNAL EXPORT_SKIP segment=%d unreadable_offset=%lu\n",
                      i,(unsigned long)pos);
        continue;
      }
      lengths[i]=lastNewline;
      total+=lastNewline;
    }
    rewind();
  }
  bool good() const {return valid;}
  size_t size() const {return total;}
  void rewind(){f.close();index=-1;remaining=0;advance();}
  int available() override {if(!remaining)advance();return (int)remaining;}
  int read() override {if(!available())return -1;int c=f.read();if(c<0){valid=false;remaining=0;return -1;}--remaining;return c;}
  size_t readBytes(char* out,size_t want) override {
    size_t got=0;
    while(got<want && available()) {
      size_t take=want-got<remaining?want-got:remaining;
      size_t n=f.read((uint8_t*)out+got,take);
      if(n!=take){valid=false;remaining=0;break;}
      got+=n;remaining-=n;
    }
    return got;
  }
  int peek() override {return available()?f.peek():-1;}
  void flush() override {}
  size_t write(uint8_t) override {return 0;}
  void close(){f.close();remaining=0;index=3;}
};
inline void status(Print& out=Serial) {
  Stats& s=stats();out.printf("NZRT JOURNAL version=JOURNAL-4-PROTOTYPE fault=%u errors=%lu verified=%lu rotations=%lu retention_discards=%lu last_ok_uptime_ms=%lu bytes=%lu limit_segment=%lu reserve=%lu quarantines=%lu export_skips=%lu retry_deferred=%lu cooldown=%u counters=since_boot\n",s.fault,(unsigned long)s.errors,(unsigned long)s.verified,(unsigned long)s.rotations,(unsigned long)s.discarded,(unsigned long)s.lastOK,(unsigned long)(sizeOf(path(0))+sizeOf(path(1))+sizeOf(path(2))),(unsigned long)SEGMENT,(unsigned long)RESERVE,(unsigned long)s.quarantines,(unsigned long)s.skippedSegments,(unsigned long)s.deferred,(unsigned)coolingDown());
}
inline bool dump() {
  Reader r;char buf[512];
  while(r.available()){size_t n=r.readBytes(buf,sizeof(buf));if(n)Serial.write((const uint8_t*)buf,n);if(!r.good() || !n)break;}
  if(!r.good())fail("dump_read");
  return r.good();
}
inline bool erase() {
  bool ok=true;
  for(int i=0;i<3;++i)
    if(SPIFFS.exists(path(i)) && !SPIFFS.remove(path(i)))ok=false;
  if(SPIFFS.exists(QUARANTINE) && !SPIFFS.remove(QUARANTINE))ok=false;
  if(!ok) fail("erase"); else {stats().consecutive=0;stats().retryAfter=0;stats().fault=false;}
  return ok;
}
inline void test() {Writer w;if(w){w.printf("NZRT JOURNAL_TEST uptime_ms=%lu\n",(unsigned long)millis());bool ok=w.close();Serial.printf("NZRT JOURNAL_TEST result=%s\n",ok?"PASS":"FAIL");}status();}
}
