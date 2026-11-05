#pragma once
// Main-loop only. Never call from the audio tasks or interrupt handlers.
#include <Arduino.h>
#include <SPIFFS.h>
#include <Stream.h>
namespace WildlifeJournal {
static constexpr size_t SEGMENT = 256UL*1024UL;
static constexpr size_t RESERVE = 384UL*1024UL;
inline const char* path(int i) { return i==0?"/packet_log.2":i==1?"/packet_log.1":"/packet_log"; }
struct Stats { uint32_t errors=0, verified=0, rotations=0, discarded=0, lastOK=0; bool fault=false; };
inline Stats& stats() { static Stats s; return s; }
inline void fail(const char* why) {
  Stats& s=stats(); ++s.errors;s.fault=true;
  Serial.printf("NZRT JOURNAL ERROR reason=%s errors=%lu\n",why,(unsigned long)s.errors);
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
class Writer : public Print {
  File f; size_t start=0,count=0; uint32_t hash=2166136261UL; bool bad=false,done=false,ok=false;
public:
  Writer() {
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
    used=SPIFFS.usedBytes();
    if(used>total || total-used<RESERVE) {fail("low_space");return;}
    // Separate an interrupted record from the next valid one.
    File tail; if(SPIFFS.exists(path(2)))tail=SPIFFS.open(path(2),FILE_READ);bool newline=false;
    if(tail && tail.size()) {tail.seek(tail.size()-1);newline=tail.read()!='\n';}
    tail.close();
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
    else {++stats().verified;stats().lastOK=millis();stats().fault=false;}
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
    for(int i=0;i<3;++i) {
      if(!SPIFFS.exists(path(i)))continue;
      File r=SPIFFS.open(path(i),FILE_READ);
      if(!r) {if(SPIFFS.exists(path(i)))valid=false;continue;}
      size_t n=r.size();uint8_t buf[512];
      // Find the last newline, scanning backwards without loading the file.
      while(n) {
        size_t begin=n>sizeof(buf)?n-sizeof(buf):0,want=n-begin;
        if(!r.seek(begin) || r.read(buf,want)!=want){valid=false;break;}
        bool found=false;
        for(size_t j=want;j>0;--j)if(buf[j-1]=='\n'){lengths[i]=begin+j;found=true;break;}
        if(found)break;
        n=begin;
      }
      r.close();total+=lengths[i];
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
  Stats& s=stats();out.printf("NZRT JOURNAL version=JOURNAL-2 fault=%u errors=%lu verified=%lu rotations=%lu retention_discards=%lu last_ok_uptime_ms=%lu bytes=%lu limit_segment=%lu reserve=%lu counters=since_boot\n",s.fault,(unsigned long)s.errors,(unsigned long)s.verified,(unsigned long)s.rotations,(unsigned long)s.discarded,(unsigned long)s.lastOK,(unsigned long)(sizeOf(path(0))+sizeOf(path(1))+sizeOf(path(2))),(unsigned long)SEGMENT,(unsigned long)RESERVE);
}
inline bool dump() {
  Reader r;char buf[512];
  while(r.available()){size_t n=r.readBytes(buf,sizeof(buf));if(n)Serial.write((const uint8_t*)buf,n);if(!r.good() || !n)break;}
  if(!r.good())fail("dump_read");
  return r.good();
}
inline bool erase() {bool ok=true;for(int i=0;i<3;++i)if(SPIFFS.exists(path(i)) && !SPIFFS.remove(path(i)))ok=false;if(!ok)fail("erase");return ok;}
inline void test() {Writer w;if(w){w.printf("NZRT JOURNAL_TEST uptime_ms=%lu\n",(unsigned long)millis());bool ok=w.close();Serial.printf("NZRT JOURNAL_TEST result=%s\n",ok?"PASS":"FAIL");}status();}
}
