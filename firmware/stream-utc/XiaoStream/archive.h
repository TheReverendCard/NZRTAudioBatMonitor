#pragma once
// All SD calls in this file require the shared SD/SX1262 bus mutex.
static uint32_t crc32buf(const void* data, size_t size, uint32_t crc=0) {
    return esp_rom_crc32_le(crc, static_cast<const uint8_t*>(data), size);
}
static bool exactFile(const String& path, const void *data, size_t size) {
    File f=SD.open(path);
    if(!f || f.size()!=size) return false;
    uint8_t block[512];
    const uint8_t *p=static_cast<const uint8_t*>(data);
    while(size) {
        size_t n=std::min(sizeof block,size);
        if(f.read(block,n)!=n || memcmp(block,p,n)) return false;
        size-=n; p+=n;
    }
    return true;
}
static bool publishSmall(const String& path,const void* data,size_t size) {
    if(storageLatched) return false;
    if(SD.exists(path)) return exactFile(path,data,size);
    String temp=path+".tmp";
    File f=SD.open(temp,FILE_WRITE);
    if(!f) return false;
    bool ok=f.write(static_cast<const uint8_t*>(data),size)==size;
    f.flush(); f.close();
    return ok && exactFile(temp,data,size) && SD.rename(temp,path);
}
struct EventRecord { Event event; uint32_t crc; } __attribute__((packed));
static_assert(sizeof(Event)==24,"stable card record");
static String eventBase(const String& dir,const Event& e) {
    char name[60];
    snprintf(name,sizeof name,"/%08lu_%010lld_%s",(unsigned long)e.id,(long long)e.ms,e.manual?"test":"event");
    return dir+name;
}
static bool storeEvent(const String& base,const Event& e) {
    EventRecord r={e,crc32buf(&e,sizeof e)};
    return publishSmall(base+".evt",&r,sizeof r);
}
static bool readEvent(const String& base,Event& e) {
    EventRecord r{};
    File f=SD.open(base+".evt");
    if(!f || f.size()!=sizeof r || f.read((uint8_t*)&r,sizeof r)!=sizeof r) return false;
    memcpy(&e,&r.event,sizeof e);
    return r.crc==crc32buf(&e,sizeof e) && e.id && e.ms>=0 && e.pre<=HISTORY*FRAME && e.manual<=1;
}
static streamclock::Anchor sessionClock(const String& dir,int64_t up) {
    streamclock::Anchor best{};
    if(dir==sessionDir && anchor.source!=streamclock::Source::unknown) best=anchor;
    if(!SD.exists(dir+"/clock.csv")) return best;
    File f=SD.open(dir+"/clock.csv");
    char row[100],boot[9],source[16],end[5];
    long long at=0,utc=0;
    while(f && f.available()) {
        size_t n=f.readBytesUntil('\n',row,sizeof row-1); row[n]=0;
        if(sscanf(row,"%8[0-9A-F],%lld,%lld,%15[A-Z_],%4s",boot,&at,&utc,source,end)!=5 ||
           strcmp(end,"END") || dir.substring(dir.lastIndexOf('/')+1)!=boot || at<0 ||
           !streamclock::validEpoch(utc/1000)) continue;
        auto s=!strcmp(source,"WIFI_NTP")?streamclock::Source::ntp:
               !strcmp(source,"LORA_OTD")?streamclock::Source::lora:streamclock::Source::unknown;
        if(s!=streamclock::Source::unknown && (best.source==streamclock::Source::unknown ||
            llabs(up-at)<llabs(up-best.up))) best={at,utc,s};
    }
    return best;
}
