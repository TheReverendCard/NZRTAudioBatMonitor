#include <Arduino.h>
#include <SD.h>
#include <SPI.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <esp_rom_crc.h>
#include <esp_sleep.h>
#include <algorithm>
#include "field.h"
#include <driver/i2s_std.h>
#include <esp_heap_caps.h>
#include <esp_timer.h>
#include <esp_sntp.h>
#include <atomic>
#include "clock_radio.h"
#include "scorer.h"
#include "pulse_train.h"
#include "pdm.h"

static constexpr char VERSION[]="XIAO-STREAM-04";
static constexpr int FRAME=512, HISTORY=94, CLIP=750, SLOTS=2;
static constexpr int MIC_CLK=1,MIC_DATA=2,UNWIRED_WS=4,SD_CS=43,RADIO_CS=41;
static constexpr int UDP_PORT=8768;
// Values 0 and 1 preserve the existing on-card event and manual test records.
enum class Trigger : uint32_t { frame = 0, manual = 1, pulse = 2 };
static const char* eventKind(Trigger trigger) {
    if (trigger == Trigger::pulse) return "pulse";
    return trigger == Trigger::manual ? "test" : "event";
}
struct Event { int64_t ms; uint32_t id; int32_t score; uint32_t pre; Trigger trigger; };
static bool recordPulseTrains, uploadWavs, referenceScorer;
static std::atomic<uint32_t> profileFrames{0}, decodeUs{0}, scoreUs{0};
static std::atomic<uint32_t> pulseTrains{0}, pulseMarkErrors{0};
struct Clip { Event event; int16_t* pcm; int frames,pre; bool pulseSupported; };
static Clip clips[SLOTS];
static Scorer scorer;
static PdmDecoder decoder;
static int16_t *history;
static int histPos,histCount,slotCount;
static bool recording[SLOTS];
static std::atomic<bool> pauseRequested{false},capturePaused{false};
static std::atomic<unsigned> outstanding{0};
static std::atomic<uint32_t> longestCommitMs{0};
static int64_t awakeUntil=90000;
static String device,token;
static Preferences storagePrefs;
static bool prefsReady;
static std::atomic<bool> storageLatched{false};
static uint32_t rescued;
static void latchStorage() {
    if(!storageLatched.exchange(true)) {
        if(prefsReady) storagePrefs.putBool("blocked",true);
        Serial.println("SD_WRITE_FAULT writes blocked");
    }
}
static uint32_t bootId;
static char sessionDir[32];
static QueueHandle_t freeSlots,writeQueue,rescueQueue,alerts;
static i2s_chan_handle_t rxChannel;
static volatile uint32_t rxOverflow;
static std::atomic<uint32_t> frames{0}, gaps{0}, detections{0}, saved{0}, missedClips{0}, lostAlerts{0};
static std::atomic<int> density{0};
static std::atomic<bool> manualClip{false};
static bool sdReady,ready,wifiConfigured,reportsConfigured;
static String ssid,key;
static SemaphoreHandle_t bus;
static IPAddress destination;
static WiFiUDP udp;
#include "clock_service.h"
#include "archive.h"
#include "delivery.h"

static void setupStorage() {
    // Both devices share SPI. Deselect the Wio before putting the card into SPI mode.
    pinMode(RADIO_CS,OUTPUT); digitalWrite(RADIO_CS,HIGH);
    pinMode(SD_CS,OUTPUT); digitalWrite(SD_CS,HIGH);
    SPI.begin(7,8,9,SD_CS);
    snprintf(sessionDir,sizeof sessionDir,"/STREAM03/%08lX",(unsigned long)bootId);
    if(!SD.begin(SD_CS,SPI,10000000)) return;
    if(!storageLatched) {
        sdReady=(SD.exists("/STREAM03") || SD.mkdir("/STREAM03")) && !SD.exists(sessionDir) && SD.mkdir(sessionDir);
        if(!sdReady) latchStorage();
    }
    if(sdReady && !mark(String(sessionDir)+"/stream04.id")) latchStorage();
    uploadWavs=SD.exists("/stream-wav.on");
    referenceScorer=SD.exists("/stream-reference.on");
    scorer.useReference(referenceScorer);
    recordPulseTrains = SD.exists("/stream-pulse.on");
    // Change CPU speed before enabling either I2S or Wi-Fi. Log the achieved MHz.
    if(SD.exists("/stream-160mhz.on") && !setCpuFrequencyMhz(160)) Serial.println("CPU 160 MHz request failed");
    File cfg=SD.open("/stream-wifi.txt",FILE_READ);
    if(!cfg) return;
    ssid=cfg.readStringUntil('\n'); key=cfg.readStringUntil('\n');
    String ip=cfg.available()?cfg.readStringUntil('\n'):"";
    token=cfg.available()?cfg.readStringUntil('\n'):String("");
    cfg.close(); ip.trim(); token.trim();
    if(ssid.endsWith("\r")) ssid.remove(ssid.length()-1);
    if(key.endsWith("\r")) key.remove(key.length()-1);
    wifiConfigured=ssid.length()>0;
    reportsConfigured=wifiConfigured && destination.fromString(ip) && uint32_t(destination)!=0;
}
static bool IRAM_ATTR overflowISR(i2s_chan_handle_t,i2s_event_data_t*,void*) {
    ++rxOverflow; return false;
}
static bool startI2S() {
    i2s_chan_config_t c=I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0,I2S_ROLE_MASTER);
    c.dma_desc_num=16; c.dma_frame_num=256;
    if(i2s_new_channel(&c,nullptr,&rxChannel)!=ESP_OK) return false;
    i2s_std_config_t s={};
    s.clk_cfg=I2S_STD_CLK_DEFAULT_CONFIG(64000);
    s.slot_cfg=I2S_STD_MSB_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT,I2S_SLOT_MODE_STEREO);
    s.gpio_cfg.bclk=gpio_num_t(MIC_CLK); s.gpio_cfg.ws=gpio_num_t(UNWIRED_WS);
    s.gpio_cfg.din=gpio_num_t(MIC_DATA); s.gpio_cfg.dout=I2S_GPIO_UNUSED; s.gpio_cfg.mclk=I2S_GPIO_UNUSED;
    i2s_event_callbacks_t callbacks={}; callbacks.on_recv_q_ovf=overflowISR;
    if(i2s_channel_init_std_mode(rxChannel,&s)!=ESP_OK ||
       i2s_channel_register_event_callback(rxChannel,&callbacks,nullptr)!=ESP_OK ||
       i2s_channel_enable(rxChannel)!=ESP_OK) return false;
    delay(120);
    s.clk_cfg=I2S_STD_CLK_DEFAULT_CONFIG(96000);
    return i2s_channel_disable(rxChannel)==ESP_OK &&
        i2s_channel_reconfig_std_clock(rxChannel,&s.clk_cfg)==ESP_OK &&
        i2s_channel_enable(rxChannel)==ESP_OK;
}
static void startClip(Event& event, bool pulseSupported) {
    int slot;
    if(!history || !histCount || xQueueReceive(freeSlots,&slot,0)!=pdTRUE) { ++missedClips; return; }
    Clip &c=clips[slot]; event.pre=histCount*FRAME; c.event=event; c.frames=c.pre=histCount;
    c.pulseSupported = pulseSupported;
    int first=(histPos+HISTORY-histCount)%HISTORY;
    int n=min(histCount,HISTORY-first);
    memcpy(c.pcm,history+first*FRAME,n*FRAME*2);
    memcpy(c.pcm+n*FRAME,history,(histCount-n)*FRAME*2);
    ++outstanding; recording[slot]=true;
}
static void captureTask(void*) {
    uint16_t raw[FRAME]; int16_t pcm[FRAME];
    uint32_t eventId=0,lastHit=0,lastOverflow=rxOverflow;
    bool haveHit=false, haveTrain=false;
    uint32_t lastTrain=0;
    pulse_train::Detector pulseDetector;
    unsigned profileTick=0;
    for(;;) {
        if(pauseRequested && !outstanding.load()) {
            i2s_channel_disable(rxChannel);
            capturePaused=true;
            while(pauseRequested) delay(20);
            scorer.reset(); decoder.reset(); histCount=histPos=0; haveHit=false;
            pulseDetector.reset(); haveTrain=false;
            i2s_channel_enable(rxChannel); lastOverflow=rxOverflow;
            capturePaused=false;
        }
        size_t n=0;
        esp_err_t rc=i2s_channel_read(rxChannel,raw,sizeof raw,&n,500);
        uint32_t currentOverflow=rxOverflow; bool overflow=currentOverflow!=lastOverflow;
        lastOverflow=currentOverflow;
        if(rc!=ESP_OK || n!=sizeof raw || overflow) {
            ++gaps; scorer.reset(); decoder.reset(); histCount=histPos=0; haveHit=false;
            pulseDetector.reset(); haveTrain=false;
            for(int i=0;i<SLOTS;++i) if(recording[i]) {
                recording[i]=false; xQueueSend(freeSlots,&i,0); --outstanding; ++missedClips;
            }
            continue;
        }
        bool sampleCost=(profileTick++%128)==0;
        if(sampleCost) {
            int ones=0;
            for(uint16_t word : raw) ones+=__builtin_popcount(word);
            density=1000*ones/(FRAME*16);
        }
        int64_t startUs=sampleCost?esp_timer_get_time():0;
        for(int i=0;i<FRAME;++i) pcm[i]=decoder.sample(raw[i]);
        const int64_t decodedAt=sampleCost?esp_timer_get_time():0;
        ++frames;
        int32_t score=0;
        bool scored = scorer.evaluate(pcm,score);
        if(sampleCost) {
            decodeUs+=uint32_t(decodedAt-startUs);
            scoreUs+=uint32_t(esp_timer_get_time()-decodedAt);
            ++profileFrames;
        }
        bool strong = scored && score >= model::cutoff;
        bool train = scored && pulseDetector.update(score);
        for(int i=0;i<SLOTS;++i) if(recording[i]) {
            Clip &c=clips[i];
            if (train) c.pulseSupported=true;
            memcpy(c.pcm+c.frames*FRAME,pcm,sizeof pcm);
            if(++c.frames==CLIP) { recording[i]=false; xQueueSend(writeQueue,&i,0); }
        }
        if(history) {
            memcpy(history+histPos*FRAME,pcm,sizeof pcm);
            histPos=(histPos+1)%HISTORY; histCount=min(HISTORY,histCount+1);
        }
        uint32_t now=millis();
        if (train) {
            if (!haveTrain || now-lastTrain >= 1000) ++pulseTrains;
            lastTrain=now; haveTrain=true;
        }
        bool hit = strong || (recordPulseTrains && train);
        bool newHit=hit && (!haveHit || now-lastHit>=1000);
        if(hit) { haveHit=true; lastHit=now; }
        bool manual=manualClip.exchange(false);
        if((newHit || manual) && !pauseRequested) {
            Trigger trigger = Trigger::manual;
            if (newHit) trigger = strong ? Trigger::frame : Trigger::pulse;
            Event event={uptimeMs(),++eventId,score,0,trigger};
            if(newHit) ++detections;
            startClip(event, train);
            if(xQueueSend(alerts,&event,0)!=pdTRUE) ++lostAlerts;
        }
    }
}
static void writeLE(uint8_t *dst,uint32_t n,int bytes) {
    for(int i=0;i<bytes;++i) dst[i]=n>>(8*i);
}
static void wavHeader(uint8_t* header,uint32_t bytes) {
    memset(header,0,44); memcpy(header,"RIFF",4); memcpy(header+8,"WAVEfmt ",8); memcpy(header+36,"data",4);
    writeLE(header+4,36+bytes,4); writeLE(header+16,16,4); writeLE(header+20,1,2); writeLE(header+22,1,2);
    writeLE(header+24,192000,4); writeLE(header+28,384000,4); writeLE(header+32,2,2);
    writeLE(header+34,16,2); writeLE(header+40,bytes,4);
}
static bool saveClip(const Clip &c) {
    String base=eventBase(sessionDir,c.event),part=base+".part",path=base+".wav";
    if(!storeEvent(base,c.event) || SD.exists(path)) return false;
    File f=SD.open(part,FILE_WRITE); if(!f) return false;
    uint32_t bytes=c.frames*FRAME*2;
    uint8_t header[44]; wavHeader(header,bytes);
    bool ok=f.write(header,sizeof header)==sizeof header;
    const uint8_t* src=(const uint8_t*)c.pcm;
    for(size_t pos=0;ok && pos<bytes;) {
        size_t n=min(size_t(8192),size_t(bytes-pos)); ok=f.write(src+pos,n)==n; pos+=n;
    }
    f.flush(); ok=ok && f.size()==sizeof header+bytes; f.close();
    if(!ok) return false;
    File check=SD.open(part);
    uint8_t block[4096];
    if(!check || check.size()!=sizeof header+bytes || check.read(block,sizeof header)!=sizeof header ||
       memcmp(block,header,sizeof header)) return false;
    uint32_t crc=crc32buf(header,sizeof header);
    for(size_t pos=0;pos<bytes;pos+=sizeof block) {
        size_t n=std::min(sizeof block,size_t(bytes-pos));
        if(check.read(block,n)!=n || memcmp(block,src+pos,n)) return false;
        crc=crc32buf(block,n,crc);
    }
    check.close();
    if (!publishSmall(base+".crc",&crc,sizeof crc) || !SD.rename(part,path)) return false;
    if (c.pulseSupported && !mark(base+".p3")) ++pulseMarkErrors;
    return true;
}
static void writerTask(void*) {
    int slot;
    while(true) if(xQueueReceive(writeQueue,&slot,portMAX_DELAY)==pdTRUE) {
        xSemaphoreTake(bus,portMAX_DELAY);
        uint32_t started=millis();
        bool ok=sdReady && !storageLatched && saveClip(clips[slot]);
        if(ok) longestCommitMs=std::max(longestCommitMs.load(),uint32_t(millis()-started));
        if(!ok && sdReady) latchStorage();
        xSemaphoreGive(bus);
        if(ok) ++saved;
        else if(transferBuffer && xQueueSend(rescueQueue,&slot,0)==pdTRUE) continue;
        else ++missedClips;
        xQueueSend(freeSlots,&slot,portMAX_DELAY); --outstanding;
    }
}
// Hold only the bounded PSRAM slots while attempting emergency Wi-Fi delivery.
static void serviceRescue() {
    static int slot=-1; static int64_t expiry;
    int64_t now=uptimeMs();
    if(slot<0) {
        if(!rescueQueue || xQueueReceive(rescueQueue,&slot,0)!=pdTRUE) return;
        expiry=now+20000;
    }
    bool ok=false;
    if(now>=retryHttp) requestWifi(now);
    if(online() && now>=retryHttp) {
        Clip& c=clips[slot];
        wavHeader(transferBuffer,WAV_BYTES-44);
        memcpy(transferBuffer+44,c.pcm,WAV_BYTES-44);
        ok=post(sessionDir,c.event,anchor,transferBuffer,crc32buf(transferBuffer,WAV_BYTES),c.pulseSupported,VERSION);
    }
    if(!ok && uptimeMs()<expiry) return;
    if(ok) { ++rescued; ++ackClips; } else ++missedClips;
    xQueueSend(freeSlots,&slot,portMAX_DELAY); --outstanding; slot=-1;
}
static void health(bool final=false) {
    static int64_t next=0;
    if(!sdReady || storageLatched || (!final && uptimeMs()<next)) return;
    if(xSemaphoreTake(bus,final?portMAX_DELAY:0)!=pdTRUE) return;
    File f=SD.open(String(sessionDir)+"/health.csv",FILE_APPEND);
    char row[300];
    int n=snprintf(row,sizeof row,"\n%lld,%lld,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lld,%lu,%u,%lu,%lu,%d,%u,%lu,%lu,%lu,%u,%lld,END\n",
        (long long)uptimeMs(),(long long)anchor.at(uptimeMs()),(unsigned long)frames.load(),(unsigned long)gaps.load(),
        (unsigned long)detections.load(),(unsigned long)saved.load(),(unsigned long)missedClips.load(),
        (unsigned long)lostAlerts.load(),(unsigned long)ackEvents,(unsigned long)ackClips,(unsigned long)httpFailures,
        (unsigned long)queueErrors,(long long)wifiActiveMs(),(unsigned long)longestCommitMs.load(),final?1:0,
        (unsigned long)wifiWindow.starts,(unsigned long)udpSent,int(referenceScorer),getCpuFrequencyMhz(),
        (unsigned long)profileFrames.load(),(unsigned long)decodeUs.load(),(unsigned long)scoreUs.load(),uploadWavs?1:0,(long long)rxAccumulated);
    if(!f || n<=0 || size_t(n)>=sizeof row || f.write((const uint8_t*)row,n)!=size_t(n)) ++queueErrors;
    f.close(); xSemaphoreGive(bus); next=uptimeMs()+30*60*1000;
}
static void status() {
    Serial.printf("%s phase=%s event_ack=%lu wav_ack=%lu http_fail=%lu outbox_errors=%lu slots=%d rescue_ack=%lu sd_latched=%d pulse_mode=%s pulse_trains=%lu pulse_mark_errors=%lu\n",VERSION,
        capturePaused?"DAY_TRANSFER":"LISTENING",(unsigned long)ackEvents,(unsigned long)ackClips,
        (unsigned long)httpFailures,(unsigned long)queueErrors,slotCount,(unsigned long)rescued,int(storageLatched.load()),
        recordPulseTrains ? "record" : "shadow",(unsigned long)pulseTrains.load(),(unsigned long)pulseMarkErrors.load());
    Serial.printf("%s ready=%d clk=D0 data=D1 sd=%s clips_buffered=%d wifi=%s frames=%lu gaps=%lu pdm_ones_permille=%d events=%lu saved=%lu unsaved=%lu alert_queue_drops=%lu boot=%08lX clock=%s clock_sd=%s utc_ms=%lld lora=%s\n",
        VERSION,ready,sdReady?"mounted":"unavailable",bool(history),wifiState(),
        (unsigned long)frames.load(),(unsigned long)gaps.load(),density.load(),(unsigned long)detections.load(),
        (unsigned long)saved.load(),(unsigned long)missedClips.load(),(unsigned long)lostAlerts.load(),(unsigned long)bootId,
        streamclock::name(anchor.source),clockSdState(),(long long)anchor.at(uptimeMs()),radioState());
}
void setup() {
    Serial.begin(115200);
    char mac[16]; snprintf(mac,sizeof mac,"%012llx",(unsigned long long)(ESP.getEfuseMac()&0xffffffffffffULL));
    device=mac; bootId=esp_random(); scorer.init(); decoder.init();
    alerts=xQueueCreate(16,sizeof(Event)); writeQueue=xQueueCreate(SLOTS,sizeof(int)); freeSlots=xQueueCreate(SLOTS,sizeof(int));
    bus=xSemaphoreCreateMutex();
    if(!alerts || !writeQueue || !freeSlots || !bus) return;
    rescueQueue=xQueueCreate(SLOTS,sizeof(int));
    if(!rescueQueue) return;
    prefsReady=storagePrefs.begin("stream03",false);
    storageLatched=prefsReady && storagePrefs.getBool("blocked",false);
    setupStorage();
    if(sdReady || (uploadWavs && reportsConfigured && token.length())) {
        history=(int16_t*)ps_malloc(HISTORY*FRAME*2);
        for(int i=0;history && i<SLOTS;++i) {
            clips[i].pcm=(int16_t*)ps_malloc(CLIP*FRAME*2);
            if(clips[i].pcm) xQueueSend(freeSlots,&i,0);
        }
        slotCount=uxQueueMessagesWaiting(freeSlots);
        if(uploadWavs && reportsConfigured && token.length()) transferBuffer=(uint8_t*)ps_malloc(WAV_BYTES);
        if(!uxQueueMessagesWaiting(freeSlots) || xTaskCreatePinnedToCore(writerTask,"sd_writer",12288,nullptr,2,nullptr,0)!=pdPASS) {
            free(history); history=nullptr;
        }
    }
    if(!startI2S()) return;
    ready=xTaskCreatePinnedToCore(captureTask,"capture",8192,nullptr,4,nullptr,1)==pdPASS;
}
void loop() {
    if(!bus || !alerts) { delay(250); return; }
    serviceClock();
    static uint32_t last=0; static char cmd[20]; static size_t used=0;
    if(millis()-last>=5000) { last=millis(); status(); }
    while(Serial.available()) {
        char ch=Serial.read();
        if(ch=='\n' || ch=='\r') {
            cmd[used]=0;
            if(!strcmp(cmd,"status")) status();
            if(!strcmp(cmd,"clip") && ready) { awakeUntil=uptimeMs()+120000; pauseRequested=false; manualClip=true; }
            if(!strcmp(cmd,"transfer") && uploadWavs && reportsConfigured && token.length()) {
                forceTransferUntil=uptimeMs()+120000; scanDirty=true;
            }
            if(!strcmp(cmd,"clear-sd") && storageLatched && !outstanding && prefsReady) {
                if(storagePrefs.putBool("blocked",false)) ESP.restart();
            }
            used=0;
        } else if(used<sizeof(cmd)-1) cmd[used++]=ch;
    }
    sendUrgent();
    serviceRescue();
    health();
    Event e;
    if(alerts && xQueueReceive(alerts,&e,0)==pdTRUE) {
        char line[200];
        snprintf(line,sizeof line,"%s %s boot=%08lX seq=%lu uptime_ms=%lld score_acc=%ld threshold=%d utc_ms=%lld clock=%s kind=%s",
            VERSION,e.trigger==Trigger::manual?"TEST":"CANDIDATE",(unsigned long)bootId,(unsigned long)e.id,(long long)e.ms,(long)e.score,e.trigger==Trigger::pulse?pulse_train::scoreFloor:model::cutoff,
            (long long)anchor.at(e.ms),streamclock::name(anchor.source),eventKind(e.trigger));
        Serial.println(line);
        liveEvent(e);
        sendUrgent();
    }
    static int64_t daySince=0;
    int64_t now=uptimeMs();
    static int64_t nextSolar=0, day=0, previousAnchor=0;
    if(now>=nextSolar || anchor.up!=previousAnchor) {
        if(anchor.up!=previousAnchor) scanDirty=true;
        previousAnchor=anchor.up;
        day=field::daytimeRemaining(anchor.at(now)/1000);
        nextSolar=now+1000;
    }
    constexpr int64_t wakeGuardSeconds=300;
    bool maintenance=day>wakeGuardSeconds+60 && now>awakeUntil && ready && (sdReady || storageLatched);
    pauseRequested=maintenance;
    bool bulk=uploadWavs && transferBuffer && ((maintenance && capturePaused) || now<forceTransferUntil);
    if(maintenance && !daySince) daySince=now;
    if(!maintenance) daySince=0;
    serviceDelivery(bulk);
    if(maintenance && capturePaused && !outstanding && uxQueueMessagesWaiting(alerts)==0) {
        bool configured=reportsConfigured && token.length();
        bool clean=scanComplete && !scanDirty && !scanHadPending && !urgentCount &&
            (!uploadWavs || transferBuffer);
        if(((!configured && !urgentCount) || clean || now-daySince>=120000) && (anchorSaved || storageLatched || now-daySince>=120000)) {
            int64_t nap=std::min<int64_t>(day-wakeGuardSeconds,4*3600);
            if(configured && !clean && !storageLatched) nap=std::min<int64_t>(nap,1800);
            if(nap>5) {
                Serial.printf("%s DAY_SLEEP seconds=%lld transfer_scan_complete=%d\n",VERSION,(long long)nap,clean);
                health(true);
                xSemaphoreTake(bus,portMAX_DELAY);
                queueDir.close(); queueRoot.close();
                if(rx==Rx::listening || rx==Rx::sleeping) clockRadio.sleep(true);
                SD.end(); WiFi.mode(WIFI_OFF);
                esp_sleep_enable_timer_wakeup((uint64_t)nap*1000000ULL); esp_deep_sleep_start();
            }
        }
    }
    delay(10);
}
