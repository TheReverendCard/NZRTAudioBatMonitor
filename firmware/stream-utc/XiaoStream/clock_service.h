#pragma once
// Main loop owns clock state and RF operations. The audio task never takes
// the SPI mutex. A fresh SNTP callback supplies every Wi-Fi anchor.
static int64_t uptimeMs() { return esp_timer_get_time()/1000; }
static streamclock::Anchor anchor,ntpNotice;
static portMUX_TYPE ntpLock=portMUX_INITIALIZER_UNLOCKED;
static bool ntpPending=false,anchorSaved=false,wifiOn=false,ntpStarted=false;
static int64_t nextSave=0,wifiSince=0,nextWifi=0;
static constexpr int64_t HOUR_MS=3600000, RETRY_MS=300000;
static Module radioModule(RADIO_CS,39,42,40,SPI,SPISettings(2000000,MSBFIRST,SPI_MODE0));
static ClockRadio clockRadio(&radioModule);
static streamclock::BeaconPair beacons;
enum class Rx { cold,absent,listening,sleeping };
static Rx rx=Rx::cold;
static int64_t radioRetry=0;
static volatile uint32_t irqMillis=0;
static volatile bool haveIrq=false;
static portMUX_TYPE irqLock=portMUX_INITIALIZER_UNLOCKED;
static void IRAM_ATTR radioIrq() {
    portENTER_CRITICAL_ISR(&irqLock);
    irqMillis=uint32_t(esp_timer_get_time()/1000);
    haveIrq=true;
    portEXIT_CRITICAL_ISR(&irqLock);
}
static const char* radioState() {
    switch(rx) {
        case Rx::cold: return "starting"; case Rx::absent: return "unavailable";
        case Rx::listening: return "listening"; default: return "sleep";
    }
}
static const char* wifiState() {
    if(!wifiConfigured) return "off";
    if(!wifiOn) return "sleep";
    return WiFi.status()==WL_CONNECTED?"connected":"connecting";
}
static const char* clockSdState() {
    if(!sdReady) return "unavailable";
    if(anchor.source==streamclock::Source::unknown) return "waiting";
    return anchorSaved?"saved":"pending";
}
static void acceptTime(streamclock::Anchor a) {
    anchor=a; anchorSaved=false; nextSave=0;
    Serial.printf("%s TIME boot=%08lX uptime_ms=%lld utc_ms=%lld clock=%s\n",VERSION,
        (unsigned long)bootId,(long long)a.up,(long long)a.utc,streamclock::name(a.source));
}
static void ntpCallback(struct timeval* tv) {
    if(!tv || !streamclock::validEpoch(tv->tv_sec)) return;
    streamclock::Anchor a{uptimeMs(),int64_t(tv->tv_sec)*1000+tv->tv_usec/1000,streamclock::Source::ntp};
    portENTER_CRITICAL(&ntpLock); ntpNotice=a; ntpPending=true; portEXIT_CRITICAL(&ntpLock);
}
static void serviceWifi(int64_t now) {
    if(!wifiConfigured) return;
    if(!wifiOn && now>=nextWifi) {
        WiFi.persistent(false); WiFi.mode(WIFI_STA); WiFi.setAutoReconnect(true);
        WiFi.begin(ssid.c_str(),key.c_str()); wifiOn=true; wifiSince=now; ntpStarted=false;
    }
    if(!wifiOn) return;
    bool connected=WiFi.status()==WL_CONNECTED;
    if(connected && !ntpStarted) {
        esp_sntp_set_time_sync_notification_cb(ntpCallback);
        configTime(0,0,"time.cloudflare.com","pool.ntp.org","time.google.com");
        ntpStarted=true;
    }
    bool received;
    streamclock::Anchor a;
    portENTER_CRITICAL(&ntpLock);
    received=ntpPending; a=ntpNotice; ntpPending=false;
    portEXIT_CRITICAL(&ntpLock);
    if(received) acceptTime(a);
    if(connected && reportsConfigured) wifiSince=now;
    if((received && !reportsConfigured) || (now-wifiSince>=45000 && !(reportsConfigured && connected))) {
        WiFi.mode(WIFI_OFF); wifiOn=false;
        nextWifi=now+(received?HOUR_MS:RETRY_MS);
    }
}
static void serviceRadio(int64_t now) {
    bool fresh=anchor.source!=streamclock::Source::unknown && now-anchor.up<HOUR_MS;
    if(now<radioRetry || (fresh && rx!=Rx::listening)) return;
    if(!fresh && rx==Rx::listening && !haveIrq) return;
    if(xSemaphoreTake(bus,0)!=pdTRUE) return;
    int16_t rc=RADIOLIB_ERR_NONE;
    if(fresh) {
        rc=clockRadio.sleep(true); rx=Rx::sleeping;
    } else if(rx!=Rx::listening) {
        if(rx!=Rx::sleeping) {
            rc=clockRadio.beginClock();
            if(rc==RADIOLIB_ERR_NONE) clockRadio.setDio1Action(radioIrq);
        }
        portENTER_CRITICAL(&irqLock); haveIrq=false; portEXIT_CRITICAL(&irqLock);
        if(rc==RADIOLIB_ERR_NONE) rc=clockRadio.startReceive();
        rx=Rx::listening;
    } else {
        portENTER_CRITICAL(&irqLock);
        uint32_t irq=irqMillis; haveIrq=false;
        portEXIT_CRITICAL(&irqLock);
        // Read into a bounded buffer, reject binary, oversized and stale packets.
        size_t len=clockRadio.getPacketLength(); uint8_t data[256]={};
        int16_t readRc=(len && len<sizeof data)?clockRadio.readData(data,len):RADIOLIB_ERR_PACKET_TOO_LONG;
        rc=clockRadio.startReceive();
        uint32_t age=uint32_t(uptimeMs())-irq;
        streamclock::Beacon b;
        if(readRc==RADIOLIB_ERR_NONE && age<3000 && !memchr(data,0,len) &&
           streamclock::decode(reinterpret_cast<char*>(data),b)) {
            int64_t arrival=uptimeMs()-age;
            if(beacons.observe(b,arrival)) acceptTime({arrival,int64_t(b.epoch)*1000,streamclock::Source::lora});
        }
    }
    xSemaphoreGive(bus);
    if(rc!=RADIOLIB_ERR_NONE) { rx=Rx::absent; radioRetry=now+RETRY_MS; }
}
static void persistClock(int64_t now) {
    if(!sdReady || anchorSaved || anchor.source==streamclock::Source::unknown || now<nextSave) return;
    if(xSemaphoreTake(bus,0)!=pdTRUE) return;
    char path[64],row[112]; snprintf(path,sizeof path,"%s/clock.csv",sessionDir);
    // Leading newline isolates an interrupted append. Readers require END.
    int n=snprintf(row,sizeof row,"\n%08lX,%lld,%lld,%s,END\n",(unsigned long)bootId,
        (long long)anchor.up,(long long)anchor.utc,streamclock::name(anchor.source));
    File f=SD.open(path,FILE_APPEND);
    if(f) {
        size_t before=f.size();
        bool ok=f.write((const uint8_t*)row,n)==size_t(n);
        f.flush(); anchorSaved=ok && f.size()==before+size_t(n); f.close();
    }
    xSemaphoreGive(bus); nextSave=now+5000;
}
static void serviceClock() {
    int64_t now=uptimeMs(); serviceWifi(now); serviceRadio(uptimeMs()); persistClock(uptimeMs());
}
