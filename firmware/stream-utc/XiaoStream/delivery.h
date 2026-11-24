#pragma once
// Called only from loop(). Capture and SD writer continue during a LAN request.
static uint32_t ackEvents,ackClips,httpFailures,queueErrors;
static int64_t retryHttp,scanAfter,forceTransferUntil;
static File queueRoot,queueDir;
static bool scanComplete=false,scanHadPending=false,scanDirty=false;
static uint8_t *transferBuffer;
static constexpr size_t WAV_BYTES=44+CLIP*FRAME*2;

static String identifier(const String& dir,const Event& e) {
    char suffix[16]; snprintf(suffix,sizeof suffix,"-%lu",(unsigned long)e.id);
    return device+"-"+dir.substring(dir.lastIndexOf('/')+1)+suffix;
}
static bool post(const String& dir,const Event& e,streamclock::Anchor clock,uint8_t* audio,uint32_t crc) {
    String id=identifier(dir,e);
    char hex[9]; snprintf(hex,sizeof hex,"%08lx",(unsigned long)crc);
    NetworkClient socket;
    HTTPClient http;
    http.setConnectTimeout(1000); http.setTimeout(3500); http.setReuse(false);
    String url="http://"+destination.toString()+":8769/"+(audio?"stream-clip":"stream-event");
    if(!http.begin(socket,url)) return false;
    http.addHeader("Authorization","Bearer "+token);
    http.addHeader("X-Event-ID",id);
    http.addHeader("X-Model",field::modelSha);
    http.addHeader("X-Uptime-Ms",String((long long)e.ms));
    http.addHeader("X-Pre-Samples",String(e.pre));
    http.addHeader("X-Score",String(e.score));
    http.addHeader("X-Kind",e.manual?"test":"event");
    http.addHeader("X-Clock",streamclock::name(clock.source));
    http.addHeader("X-Trigger-UTC-Ms",String((long long)clock.at(e.ms)));
    if(audio) http.addHeader("X-WAV-CRC32",hex);
    else http.addHeader("Content-Length","0");
    int code=http.POST(audio?audio:(uint8_t*)"",audio?WAV_BYTES:0);
    String expected="OK "+id+(audio?String(" ")+hex:String(""));
    bool ok=code==200 && http.getSize()==int(expected.length()) && http.getString()==expected;
    http.end();
    if(!ok) {
        ++httpFailures; retryHttp=uptimeMs()+30000;
        Serial.printf("%s transfer_failed http=%d retry_s=30\n",VERSION,code);
    }
    return ok;
}
static bool mark(const String& path) {
    const uint8_t ok=0xA5;
    return publishSmall(path,&ok,1);
}
static bool marked(const String& path) {
    const uint8_t ok=0xA5;
    return SD.exists(path) && exactFile(path,&ok,1);
}
static Event recent;
static bool recentPending=false;
static int64_t nextReplay=0;
static bool online() { return reportsConfigured && token.length() && wifiOn && WiFi.status()==WL_CONNECTED; }
static void liveEvent(const Event& e) {
    String base=eventBase(sessionDir,e);
    bool stored=false;
    if(sdReady && !storageLatched) {
        xSemaphoreTake(bus,portMAX_DELAY); stored=storeEvent(base,e); xSemaphoreGive(bus);
    }
    if(!stored) { ++queueErrors; if(sdReady) latchStorage(); }
    if(!reportsConfigured || !token.length()) return;
    requestWifi(uptimeMs());
    scanDirty=true;
    if(!online() || uptimeMs()<retryHttp) {
        recent=e; recentPending=true;
        nextReplay=uptimeMs()+30000; return;
    }
    if(post(sessionDir,e,anchor,nullptr,0)) {
        ++ackEvents;
        if(stored) {
            xSemaphoreTake(bus,portMAX_DELAY);
            if(!mark(base+".ack") || (anchor.source!=streamclock::Source::unknown && !mark(base+".utc"))) ++queueErrors;
            xSemaphoreGive(bus);
        }
    } else nextReplay=uptimeMs()+30000;
}
static void replayRecent() {
    int64_t now=uptimeMs();
    if(nextReplay && now>=nextReplay) {
        requestWifi(now); scanDirty=true; nextReplay=now+300000;
    }
    if(!recentPending || !online() || now<retryHttp) return;
    Event e=recent; recentPending=false; liveEvent(e);
}
// Read one directory entry per tick. Keep enumeration cursors between calls.
// A verified WAV doubles as the persistent upload queue, including older boots.
static String nextEntry() {
    if(!queueRoot) {
        queueRoot=SD.open("/STREAM03");
        if(!queueRoot) { ++queueErrors; scanHadPending=true; return ""; }
    }
    if(!queueDir) {
        queueDir=queueRoot.openNextFile();
        if(!queueDir) {
            queueRoot.close(); scanComplete=true; scanAfter=uptimeMs()+60000;
            if(!scanHadPending) nextReplay=0;
            return "";
        }
        if(!queueDir.isDirectory()) queueDir.close();
        return "";
    }
    File f=queueDir.openNextFile();
    if(!f) { queueDir.close(); return ""; }
    String path=f.path(); f.close();
    return path.endsWith(".evt")?path.substring(0,path.length()-4):String("");
}
static bool readWav(const String& base,uint32_t& crc) {
    File check=SD.open(base+".crc");
    if(!check || check.size()!=sizeof crc || check.read((uint8_t*)&crc,sizeof crc)!=sizeof crc) return false;
    File f=SD.open(base+".wav");
    if(!f || f.size()!=WAV_BYTES || !transferBuffer) return false;
    return f.read(transferBuffer,WAV_BYTES)==WAV_BYTES && crc32buf(transferBuffer,WAV_BYTES)==crc;
}
static void serviceDelivery(bool bulk) {
    const int64_t now=uptimeMs();
    if(!sdReady || !online() || now<retryHttp || (now<scanAfter && !scanDirty)) return;
    if(scanComplete || scanDirty) {
        if(scanComplete) {scanHadPending=false; scanComplete=false;}
        scanAfter=0; scanDirty=false;
    }
    if(xSemaphoreTake(bus,0)!=pdTRUE) return;
    String base=nextEntry();
    if(!base.length()) {xSemaphoreGive(bus); return;}
    Event e{};
    String dir=base.substring(0,base.lastIndexOf('/'));
    bool valid=readEvent(base,e) && base==eventBase(dir,e);
    bool alert=valid && !marked(base+".ack");
    bool needsTime=valid && !marked(base+".utc");
    bool audio=bulk && valid && SD.exists(base+".wav") && !marked(base+".done");
    if(!valid) {++queueErrors; scanHadPending=true;}
    if(!valid || (!alert && !audio && !needsTime)) {xSemaphoreGive(bus);return;}
    streamclock::Anchor clock=sessionClock(dir,e.ms);
    bool timed=clock.source!=streamclock::Source::unknown;
    uint32_t crc=0;
    if(audio && (!transferBuffer || !readWav(base,crc))) {++queueErrors;scanHadPending=true;audio=false;}
    xSemaphoreGive(bus);
    if(!audio && !alert && !(needsTime && timed)) return;
    if(!post(dir,e,clock,audio?transferBuffer:nullptr,crc)) {scanHadPending=true;return;}
    if(audio) ++ackClips;
    if(alert) ++ackEvents;
    xSemaphoreTake(bus,portMAX_DELAY);
    if(!mark(base+".ack") || (timed && !mark(base+".utc")) || (audio && !mark(base+".done"))) {
        ++queueErrors;scanHadPending=true;
    }
    xSemaphoreGive(bus);
}
