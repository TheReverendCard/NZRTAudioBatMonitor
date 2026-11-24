#pragma once
// Called only from loop(). Capture and SD writer continue during a LAN request.
static uint32_t ackEvents,ackClips,httpFailures,queueErrors;
static int64_t retryHttp,scanAfter,forceTransferUntil;
static String pendingBase;
static bool bulkLast=false;
static File queueRoot,queueDir;
static bool scanComplete=false,scanHadPending=false,scanDirty=true;
static uint8_t *transferBuffer;
static constexpr size_t WAV_BYTES=44+CLIP*FRAME*2;

static String identifier(const String& dir,const Event& e) {
    char suffix[16]; snprintf(suffix,sizeof suffix,"-%lu",(unsigned long)e.id);
    return device+"-"+dir.substring(dir.lastIndexOf('/')+1)+suffix;
}
static bool post(const String& dir,const Event& e,streamclock::Anchor clock,uint8_t* audio,uint32_t crc,bool pulseSupported,const char* archiveFirmware) {
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
    http.addHeader("X-Firmware",archiveFirmware);
    http.addHeader("X-Uptime-Ms",String((long long)e.ms));
    http.addHeader("X-Pre-Samples",String(e.pre));
    http.addHeader("X-Score",String(e.score));
    http.addHeader("X-Kind",eventKind(e.trigger));
    http.addHeader("X-Clock",streamclock::name(clock.source));
    http.addHeader("X-Trigger-UTC-Ms",String((long long)clock.at(e.ms)));
    if(audio && pulseSupported) http.addHeader("X-Pulse-Evidence","train-v1");
    if(audio) http.addHeader("X-WAV-CRC32",hex);
    else http.addHeader("Content-Length","0");
    int code=http.POST(audio?audio:(uint8_t*)"",audio?WAV_BYTES:0);
    String expected="OK "+id+(audio?String(" ")+hex:String(""));
    bool ok=code==200 && http.getSize()==int(expected.length()) && http.getString()==expected;
    http.end();
    if(!ok) {
        ++httpFailures; retryHttp=uptimeMs()+300000;
        Serial.printf("%s transfer_failed http=%d retry_s=300\n",VERSION,code);
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
// RAM gives new events priority while a station association is in progress.
// Authenticated alerts also have the verified SD outbox for outage/reboot replay.
static Event urgent[16];
static unsigned urgentHead=0,urgentCount=0;
static uint32_t udpSent=0;
static bool online() { return reportsConfigured && wifiWindow.on && WiFi.status()==WL_CONNECTED; }
static void liveEvent(const Event& e) {
    if(sdReady && !storageLatched) {
        xSemaphoreTake(bus,portMAX_DELAY);
        bool stored=storeEvent(eventBase(sessionDir,e),e);
        xSemaphoreGive(bus);
        if(!stored) { ++queueErrors; latchStorage(); }
    }
    if(!reportsConfigured) return;
    scanDirty=true;
    if(urgentCount==16) { ++lostAlerts; return; }
    urgent[(urgentHead+urgentCount)%16]=e;
    ++urgentCount;
}
static void sendUrgent() {
    if(!urgentCount || uptimeMs()<retryHttp) return;
    requestWifi(uptimeMs());
    if(!online()) return;
    const Event& e=urgent[urgentHead];
    if(token.length()) {
        if(!post(sessionDir,e,anchor,nullptr,0,false,VERSION)) return;
        ++ackEvents;
        if(sdReady && !storageLatched) {
            String base=eventBase(sessionDir,e);
            xSemaphoreTake(bus,portMAX_DELAY);
            if(!mark(base+".ack") || (anchor.source!=streamclock::Source::unknown && !mark(base+".utc"))) ++queueErrors;
            xSemaphoreGive(bus);
        }
    } else {
        // The installed Trial 02 listener filters on this prefix.
        char line[240];
        int n=snprintf(line,sizeof line,"XIAO-STREAM-02 %s boot=%08lX seq=%lu uptime_ms=%lld score_acc=%ld threshold=%d utc_ms=%lld clock=%s kind=%s firmware=%s",
            e.trigger==Trigger::manual?"TEST":"CANDIDATE",(unsigned long)bootId,(unsigned long)e.id,(long long)e.ms,
            (long)e.score,e.trigger==Trigger::pulse?pulse_train::scoreFloor:model::cutoff,(long long)anchor.at(e.ms),
            streamclock::name(anchor.source),eventKind(e.trigger),VERSION);
        if(!udp.beginPacket(destination,UDP_PORT) || udp.write((const uint8_t*)line,n)!=size_t(n) || !udp.endPacket()) {
            retryHttp=uptimeMs()+300000; return;
        }
        ++udpSent;
    }
    urgentHead=(urgentHead+1)%16; --urgentCount;
}
// Read one directory entry per tick. Keep enumeration cursors between calls.
// A verified WAV doubles as the persistent upload queue, including older boots.
static String nextEntry() {
    if(!queueRoot) {
        queueRoot=SD.open("/STREAM03");
        if(!queueRoot) { ++queueErrors; scanHadPending=true; scanComplete=true; scanAfter=uptimeMs()+300000; return ""; }
    }
    if(!queueDir) {
        queueDir=queueRoot.openNextFile();
        if(!queueDir) {
            queueRoot.close(); scanComplete=true; scanAfter=uptimeMs()+300000;
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
    if(!sdReady || storageLatched || !reportsConfigured || !token.length()) return;
    bool bulkChanged=bulk!=bulkLast;
    if(bulkChanged) { bulkLast=bulk; scanDirty=true; }
    if(urgentCount || now<retryHttp) return;
    if(pendingBase.length() && !bulkChanged && !online()) {
        if(now>=wifiWindow.retryAt) requestWifi(now);
        return;
    }
    if(scanComplete) {
        if(!scanDirty && (!scanHadPending || now<scanAfter)) return;
        scanHadPending=false; scanComplete=false; scanDirty=false;
    }
    if(xSemaphoreTake(bus,0)!=pdTRUE) return;
    if(!pendingBase.length()) pendingBase=nextEntry();
    if(!pendingBase.length()) { xSemaphoreGive(bus); return; }
    String base=pendingBase;
    Event e{};
    String dir=base.substring(0,base.lastIndexOf('/'));
    bool valid=readEvent(base,e) && base==eventBase(dir,e);
    bool alert=valid && !marked(base+".ack");
    bool needsTime=valid && !marked(base+".utc");
    bool audio=bulk && valid && SD.exists(base+".wav") && !marked(base+".done");
    if(!valid) { ++queueErrors; scanHadPending=true; }
    streamclock::Anchor clock{};
    if(alert || audio || needsTime) clock=sessionClock(dir,e.ms);
    bool timed=clock.source!=streamclock::Source::unknown;
    if(!alert && !audio && !(needsTime && timed)) {
        pendingBase=""; xSemaphoreGive(bus); return;
    }
    // Keep the cursor parked on proven work during association/backoff.
    if(now<wifiWindow.retryAt || !online()) {
        if(now>=wifiWindow.retryAt) requestWifi(now);
        xSemaphoreGive(bus); return;
    }
    requestWifi(now);
    uint32_t crc=0;
    bool pulseSupported=false;
    if(audio) {
        if(!readWav(base,crc)) { ++queueErrors; scanHadPending=true; audio=false; }
        else pulseSupported=marked(base+".p3");
    }
    bool trial04=(dir==sessionDir || SD.exists(dir+"/stream04.id"));
    pendingBase="";
    xSemaphoreGive(bus);
    if(!audio && !alert && !(needsTime && timed)) return;
    if(!post(dir,e,clock,audio?transferBuffer:nullptr,crc,pulseSupported,trial04?VERSION:"XIAO-STREAM-03")) {
        scanHadPending=true; return;
    }
    if(audio) ++ackClips;
    if(alert) ++ackEvents;
    xSemaphoreTake(bus,portMAX_DELAY);
    if(!mark(base+".ack") || (timed && !mark(base+".utc")) || (audio && !mark(base+".done"))) {
        ++queueErrors; scanHadPending=true;
    }
    xSemaphoreGive(bus);
}
