#include <Arduino.h>
#include <SD.h>
#include <SPI.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <driver/i2s_std.h>
#include <esp_heap_caps.h>
#include <esp_timer.h>
#include <esp_sntp.h>
#include <atomic>
#include "clock_radio.h"
#include "scorer.h"
#include "pdm.h"

static constexpr char VERSION[]="XIAO-STREAM-02";
static constexpr int FRAME=512, HISTORY=94, CLIP=750, SLOTS=2;
static constexpr int MIC_CLK=1,MIC_DATA=2,UNWIRED_WS=4,SD_CS=43,RADIO_CS=41;
static constexpr int UDP_PORT=8768;
struct Event { uint32_t id; int64_t ms; int32_t score; bool manual; };
struct Clip { Event event; int16_t* pcm; int frames,pre; };
static Clip clips[SLOTS];
static Scorer scorer;
static PdmDecoder decoder;
static int16_t *history;
static int histPos,histCount,active=-1;
static uint32_t bootId;
static char sessionDir[32];
static QueueHandle_t freeSlots,writeQueue,alerts;
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

static void setupStorage() {
    // Both devices share SPI. Deselect the Wio before putting the card into SPI mode.
    pinMode(RADIO_CS,OUTPUT); digitalWrite(RADIO_CS,HIGH);
    pinMode(SD_CS,OUTPUT); digitalWrite(SD_CS,HIGH);
    SPI.begin(7,8,9,SD_CS);
    if(!SD.begin(SD_CS,SPI,10000000)) return;
    if(!SD.exists("/STREAM02") && !SD.mkdir("/STREAM02")) return;
    snprintf(sessionDir,sizeof sessionDir,"/STREAM02/%08lX",(unsigned long)bootId);
    if(SD.exists(sessionDir) || !SD.mkdir(sessionDir)) return;
    sdReady=true;
    File cfg=SD.open("/stream-wifi.txt",FILE_READ);
    if(!cfg) return;
    ssid=cfg.readStringUntil('\n'); key=cfg.readStringUntil('\n');
    String ip=cfg.available()?cfg.readStringUntil('\n'):"";
    cfg.close(); ip.trim();
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
static void startClip(const Event &event) {
    if(!sdReady || active>=0 || !histCount) { ++missedClips; return; }
    int slot;
    if(xQueueReceive(freeSlots,&slot,0)!=pdTRUE) { ++missedClips; return; }
    Clip &c=clips[slot]; c.event=event; c.frames=c.pre=histCount;
    int first=(histPos+HISTORY-histCount)%HISTORY;
    int n=min(histCount,HISTORY-first);
    memcpy(c.pcm,history+first*FRAME,n*FRAME*2);
    memcpy(c.pcm+n*FRAME,history,(histCount-n)*FRAME*2);
    active=slot;
}
static void captureTask(void*) {
    uint16_t raw[FRAME]; int16_t pcm[FRAME];
    uint32_t eventId=0,lastHit=0,lastOverflow=rxOverflow;
    bool haveHit=false;
    for(;;) {
        size_t n=0;
        esp_err_t rc=i2s_channel_read(rxChannel,raw,sizeof raw,&n,500);
        uint32_t currentOverflow=rxOverflow; bool overflow=currentOverflow!=lastOverflow;
        lastOverflow=currentOverflow;
        if(rc!=ESP_OK || n!=sizeof raw || overflow) {
            ++gaps; scorer.reset(); decoder.reset(); histCount=histPos=0; haveHit=false;
            if(active>=0) { xQueueSend(freeSlots,&active,0); active=-1; ++missedClips; }
            continue;
        }
        int ones=0;
        for(int i=0;i<FRAME;++i) { ones+=__builtin_popcount(raw[i]); pcm[i]=decoder.sample(raw[i]); }
        density=1000*ones/(FRAME*16);
        ++frames;
        if(active>=0) {
            Clip &c=clips[active];
            memcpy(c.pcm+c.frames*FRAME,pcm,sizeof pcm);
            if(++c.frames==CLIP) { xQueueSend(writeQueue,&active,0); active=-1; }
        }
        if(history) {
            memcpy(history+histPos*FRAME,pcm,sizeof pcm);
            histPos=(histPos+1)%HISTORY; histCount=min(HISTORY,histCount+1);
        }
        int32_t score=0;
        bool hit=scorer.evaluate(pcm,score) && score>=model::cutoff;
        uint32_t now=millis();
        bool newHit=hit && (!haveHit || now-lastHit>=1000);
        if(hit) { haveHit=true; lastHit=now; }
        bool manual=manualClip.exchange(false);
        if(newHit || manual) {
            Event event={++eventId,uptimeMs(),score,manual&&!newHit};
            if(newHit) ++detections;
            if(xQueueSend(alerts,&event,0)!=pdTRUE) ++lostAlerts;
            startClip(event);
        }
    }
}
static void writeLE(uint8_t *dst,uint32_t n,int bytes) {
    for(int i=0;i<bytes;++i) dst[i]=n>>(8*i);
}
static bool saveClip(const Clip &c) {
    char path[96],part[96]; const Event &e=c.event;
    snprintf(path,sizeof path,"%s/%08lu_%010lld_%s.wav",sessionDir,(unsigned long)e.id,
             (long long)e.ms,e.manual?"test":"event");
    snprintf(part,sizeof part,"%s/%08lu.part",sessionDir,(unsigned long)e.id);
    File f=SD.open(part,FILE_WRITE); if(!f) return false;
    uint32_t bytes=c.frames*FRAME*2;
    uint8_t header[44]={}; memcpy(header,"RIFF",4); memcpy(header+8,"WAVEfmt ",8); memcpy(header+36,"data",4);
    writeLE(header+4,36+bytes,4); writeLE(header+16,16,4); writeLE(header+20,1,2); writeLE(header+22,1,2);
    writeLE(header+24,192000,4); writeLE(header+28,384000,4); writeLE(header+32,2,2);
    writeLE(header+34,16,2); writeLE(header+40,bytes,4);
    bool ok=f.write(header,sizeof header)==sizeof header;
    const uint8_t* src=(const uint8_t*)c.pcm;
    for(size_t pos=0;ok && pos<bytes;) {
        size_t n=min(size_t(8192),size_t(bytes-pos)); ok=f.write(src+pos,n)==n; pos+=n;
    }
    f.flush(); ok=ok && f.size()==sizeof header+bytes; f.close();
    return ok && SD.rename(part,path);
}
static void writerTask(void*) {
    int slot;
    while(true) if(xQueueReceive(writeQueue,&slot,portMAX_DELAY)==pdTRUE) {
        xSemaphoreTake(bus,portMAX_DELAY);
        bool ok=saveClip(clips[slot]);
        xSemaphoreGive(bus);
        if(ok) ++saved; else ++missedClips;
        xQueueSend(freeSlots,&slot,portMAX_DELAY);
    }
}
static void status() {
    Serial.printf("%s ready=%d clk=D0 data=D1 sd=%s clips_buffered=%d wifi=%s frames=%lu gaps=%lu pdm_ones_permille=%d events=%lu saved=%lu unsaved=%lu alert_queue_drops=%lu boot=%08lX clock=%s clock_sd=%s utc_ms=%lld lora=%s\n",
        VERSION,ready,sdReady?"mounted":"unavailable",bool(history),wifiState(),
        (unsigned long)frames.load(),(unsigned long)gaps.load(),density.load(),(unsigned long)detections.load(),
        (unsigned long)saved.load(),(unsigned long)missedClips.load(),(unsigned long)lostAlerts.load(),(unsigned long)bootId,
        streamclock::name(anchor.source),clockSdState(),(long long)anchor.at(uptimeMs()),radioState());
}
void setup() {
    Serial.begin(115200); bootId=esp_random(); scorer.init(); decoder.init();
    alerts=xQueueCreate(16,sizeof(Event)); writeQueue=xQueueCreate(SLOTS,sizeof(int)); freeSlots=xQueueCreate(SLOTS,sizeof(int));
    bus=xSemaphoreCreateMutex();
    if(!alerts || !writeQueue || !freeSlots || !bus) return;
    setupStorage();
    if(sdReady) {
        history=(int16_t*)ps_malloc(HISTORY*FRAME*2);
        for(int i=0;history && i<SLOTS;++i) {
            clips[i].pcm=(int16_t*)ps_malloc(CLIP*FRAME*2);
            if(clips[i].pcm) xQueueSend(freeSlots,&i,0);
        }
        if(!uxQueueMessagesWaiting(freeSlots) || xTaskCreatePinnedToCore(writerTask,"sd_writer",6144,nullptr,2,nullptr,0)!=pdPASS) {
            free(history); history=nullptr;
        }
    }
    if(!startI2S()) return;
    ready=xTaskCreatePinnedToCore(captureTask,"capture",8192,nullptr,4,nullptr,1)==pdPASS;
}
void loop() {
    if(bus) serviceClock();
    static uint32_t last=0; static char cmd[20]; static size_t used=0;
    if(millis()-last>=5000) { last=millis(); status(); }
    while(Serial.available()) {
        char ch=Serial.read();
        if(ch=='\n' || ch=='\r') {
            cmd[used]=0;
            if(!strcmp(cmd,"status")) status();
            if(!strcmp(cmd,"clip") && ready) manualClip=true;
            used=0;
        } else if(used<sizeof(cmd)-1) cmd[used++]=ch;
    }
    Event e;
    if(alerts && xQueueReceive(alerts,&e,0)==pdTRUE) {
        char line[200];
        snprintf(line,sizeof line,"%s %s boot=%08lX seq=%lu uptime_ms=%lld score_acc=%ld threshold=%d utc_ms=%lld clock=%s",
            VERSION,e.manual?"TEST":"CANDIDATE",(unsigned long)bootId,(unsigned long)e.id,(long long)e.ms,(long)e.score,model::cutoff,
            (long long)anchor.at(e.ms),streamclock::name(anchor.source));
        Serial.println(line);
        if(reportsConfigured && wifiOn && WiFi.status()==WL_CONNECTED && udp.beginPacket(destination,UDP_PORT)) {
            udp.write((const uint8_t*)line,strlen(line)); udp.endPacket();
        }
    }
    delay(1);
}
