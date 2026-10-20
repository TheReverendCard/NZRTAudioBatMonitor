/*
XIAO bat overnight pilot v1.0.2 candidate
Target: Arduino ESP32 3.3.12, XIAO ESP32S3, OPI PSRAM, USB CDC On Boot.

EDIT WIFI_SSID and WIFI_PASSWORD BELOW before uploading. Use a 2.4GHz network.
Coordinates are approximate Maunu, not a surveyed property location.

Startup: connect WiFi and obtain fresh NTP time; mount/check SD; record a
10-second startup WAV; save; enter daytime idle or the overnight schedule.
At night: monitor from sunset minus 20 minutes until sunrise. Save candidate
ultrasonic events plus a fixed 10-second sample every 5 minutes (and at start).
Triggered WAVs include up to 0.5s pretrigger, extend 3s after the last candidate,
and are capped at 10s. Candidate != confirmed bat. 96kHz mono PCM16.
The broad 20kHz high-pass detector uses 2x background RMS (minimum4 PCM LSB),
one 512-sample window. Deliberately more permissive than the rubbing bench test.
43kHz anti-alias filter attenuates upper calls; this is an experimental recorder.

LED (active-low user LED GPIO21, not the charge LED):
  one short flash / 2s: listening, awaiting event
  two short flashes / 2s: recording into RAM
  solid: SD work or microphone startup/calibration
  three short flashes / 3s: DAYTIME SAFE, card unmounted
  four short flashes / 2s: WiFi/time sync in progress
  fast continuous flashing: fault (time, SD or capture); automatic retries

DAYTIME COLLECTION: wait for the three-flash safe indication, disconnect power,
remove SD, copy files, safely eject from computer, replace SD, reconnect power.
WiFi must be reachable again after power loss. Never remove SD while solid or
one/two flashes. Daytime safe performs no SD operations until the next session.
No deep sleep. Safe daytime idle may reduce CPU frequency to80MHz.
The boot-selected CPU frequency is restored before WiFi, SD or audio work.
Connecting Serial Monitor keeps the CPU at its active frequency. Use a
powerbank that stays on at low loads; measure before assuming longer runtime.

Clock: sync at boot, then daily from local noon while idle; failed daily syncs
retry every15min until monitoring starts. If a daily sync fails, keep the running
clock and log its last sync. After reset, require a NEW successful sync; no guessed
calendar dates. UTC filenames/logs; NZ local time only for schedule/status.
Radio is disabled before audio capture. No web interface or LoRa transmission.

Files: /night_YYYYMMDDTHHMMSSZ_NNN/ or /startup_.../ with session.txt and WAVs.
CSV-like key=value logs: schedule, reset cause, time-sync state, events, payload
FNV-1a hashes, sample counts, clipping, failures, listen spans and blind intervals.
Blind-start bounds include queued DMA audio (up to42.667ms). WAV UTC start is
estimated from the first read of each continuous run; it is not hardware-timed.
Sample clock drift/latency remain to be measured against AR4. No full SD readback.
No SD operations while listening. Incomplete run after power loss can leave an
unfinished last WAV/log; earlier flushed files should still be checked offline.

Serial Monitor 115200: send s for status while idle/sync/fault waiting.
Configuration faults repeat every5s; status prints when USB monitor connects.
No libraries beyond the ESP32 board package. Do not change the working wiring:
mic CLK GPIO3, DATA GPIO4, SELECT low; GPIO5 dummy WS must remain unconnected.
SD SCK7 MISO8 MOSI9 CS43 at4MHz. Future LoRa CS41 held HIGH.

Credits: https://github.com/meerstern/SPH0641LU
https://github.com/AkiyukiOkayasu/pico-PDM
https://github.com/adafruit/Adafruit-microSD-Card-BFF-PCB
Solar equations: https://gml.noaa.gov/grad/solcalc/solareqns.PDF
*/

#include <Arduino.h>

// ======================== USER SETTINGS ========================
const char *WIFI_SSID = "YOUR_WIFI_NAME";
const char *WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
constexpr double SITE_LATITUDE = -35.75;   // South is negative.
constexpr double SITE_LONGITUDE = 174.27; // East is positive.
constexpr int START_BEFORE_SUNSET_MIN = 20;
constexpr uint32_t PERIODIC_SECONDS = 300;
constexpr uint32_t PERIODIC_CLIP_SECONDS = 10;
constexpr uint32_t MAX_CLIP_SECONDS = 10;
constexpr uint32_t POST_EVENT_SECONDS = 3;
constexpr float TRIGGER_RMS_MULTIPLIER = 2.0f;
constexpr float MIN_TRIGGER_RMS = 4.0f;
constexpr bool ENABLE_DAYTIME_CPU_REDUCTION = true;
constexpr uint32_t DAYTIME_CPU_MHZ = 80;
const char *NZ_TIMEZONE = "NZST-12NZDT,M9.5.0/2,M4.1.0/3";
// ===============================================================
#include <Arduino.h>
#include <SPI.h>
#include <SD.h>
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "driver/i2s_common.h"
#include "driver/i2s_pdm.h"
#include "driver/i2s_std.h"

#ifndef D2
#define D2 3
#endif

#ifndef D3
#define D3 4
#endif

#ifndef D4
#define D4 5
#endif

static constexpr gpio_num_t MIC_CLK_PIN  = (gpio_num_t)D2;
static constexpr gpio_num_t MIC_DATA_PIN = (gpio_num_t)D3;
static constexpr gpio_num_t DUMMY_WS_PIN = (gpio_num_t)D4;

// Hardware-PDM PCM rates
static constexpr uint32_t AUDIBLE_PCM_RATE = 32000;
static constexpr uint32_t HW_ULTRA_PCM_RATE = 64000;

// STD-I2S raw sampler:
// 96 kHz frames * 2 slots * 16 bits = 3.072 MHz BCLK
static constexpr uint32_t RAW_I2S_FRAME_RATE = 96000;

enum StreamMode : uint8_t {
  MODE_NONE       = 0,
  MODE_AUDIBLE    = 1,
  MODE_HW_ULTRA   = 2,
  MODE_RAW_STD    = 3
};

static StreamMode current_mode = MODE_NONE;
static i2s_chan_handle_t rx_chan = nullptr;

#pragma pack(push, 1)
struct PacketHeader {
  uint32_t magic;
  uint8_t mode;
  uint8_t reserved;
  uint16_t payload_len;
  uint32_t sequence;
};
#pragma pack(pop)

static constexpr uint32_t PACKET_MAGIC = 0x4D4B5044;
static uint32_t sequence_number = 0;

// 2048 keeps USB overhead modest while remaining well below uint16 payload size.
static uint8_t io_buffer[2048];

static void destroyI2S() {
  if (rx_chan != nullptr) {
    esp_err_t err = i2s_channel_disable(rx_chan);
    (void)err;
    i2s_del_channel(rx_chan);
    rx_chan = nullptr;
  }

  current_mode = MODE_NONE;
  sequence_number = 0;
}

static volatile bool trackOverflows = false;
static volatile uint32_t overflowCount = 0;
static bool IRAM_ATTR overflowCallback(i2s_chan_handle_t,
                                       i2s_event_data_t *, void *) {
  if (trackOverflows) overflowCount=overflowCount+1;
  return false;
}

static bool makeRxChannel() {
  i2s_chan_config_t chan_cfg =
    I2S_CHANNEL_DEFAULT_CONFIG(
      I2S_NUM_0,
      I2S_ROLE_MASTER
    );

  // Give the faster raw sampler comfortable DMA buffering.
  chan_cfg.dma_desc_num = 8;
  chan_cfg.dma_frame_num = 512;

  esp_err_t err =
    i2s_new_channel(
      &chan_cfg,
      nullptr,
      &rx_chan
    );

  if (err == ESP_OK) {
    i2s_event_callbacks_t callbacks = {};
    callbacks.on_recv_q_ovf = overflowCallback;
    err = i2s_channel_register_event_callback(rx_chan, &callbacks, nullptr);
  }
  return err == ESP_OK;
}

static bool initPdmPcm(uint32_t pcm_rate) {
  destroyI2S();

  if (!makeRxChannel()) {
    return false;
  }

  i2s_pdm_rx_config_t cfg = {
    .clk_cfg =
      I2S_PDM_RX_CLK_DEFAULT_CONFIG(
        pcm_rate
      ),

    .slot_cfg =
      I2S_PDM_RX_SLOT_PCM_FMT_DEFAULT_CONFIG(
        I2S_DATA_BIT_WIDTH_16BIT,
        I2S_SLOT_MODE_MONO
      ),

    .gpio_cfg = {
      .clk = MIC_CLK_PIN,
      .din = MIC_DATA_PIN,
      .invert_flags = {
        .clk_inv = false,
      },
    },
  };

  // Your breakout's SELECT is strapped LOW -> LEFT.
  cfg.slot_cfg.slot_mask = I2S_PDM_SLOT_LEFT;

  // DSR_8S: external PDM CLK = PCM sample rate * 64.
  cfg.clk_cfg.dn_sample_mode = I2S_PDM_DSR_8S;

  esp_err_t err =
    i2s_channel_init_pdm_rx_mode(
      rx_chan,
      &cfg
    );

  if (err != ESP_OK) {
    destroyI2S();
    return false;
  }

  err = i2s_channel_enable(
    rx_chan
  );

  if (err != ESP_OK) {
    destroyI2S();
    return false;
  }

  return true;
}

static bool enterAudible() {
  if (!initPdmPcm(AUDIBLE_PCM_RATE)) {
    return false;
  }

  // 2.048 MHz microphone clock, safely in standard mode.
  delay(100);

  current_mode = MODE_AUDIBLE;
  sequence_number = 0;
  return true;
}

static bool initStdRawAtFrameRate(uint32_t frame_rate) {
  destroyI2S();

  if (!makeRxChannel()) {
    return false;
  }

  i2s_std_config_t cfg = {
    .clk_cfg =
      I2S_STD_CLK_DEFAULT_CONFIG(
        frame_rate
      ),

    .slot_cfg =
      I2S_STD_MSB_SLOT_DEFAULT_CONFIG(
        I2S_DATA_BIT_WIDTH_16BIT,
        I2S_SLOT_MODE_STEREO
      ),

    .gpio_cfg = {
      .mclk = I2S_GPIO_UNUSED,
      .bclk = MIC_CLK_PIN,
      .ws   = DUMMY_WS_PIN,
      .dout = I2S_GPIO_UNUSED,
      .din  = MIC_DATA_PIN,
      .invert_flags = {
        .mclk_inv = false,
        .bclk_inv = false,
        .ws_inv = false,
      },
    },
  };

  esp_err_t err =
    i2s_channel_init_std_mode(
      rx_chan,
      &cfg
    );

  if (err != ESP_OK) {
    destroyI2S();
    return false;
  }

  err = i2s_channel_enable(
    rx_chan
  );

  if (err != ESP_OK) {
    destroyI2S();
    return false;
  }

  return true;
}

static bool enterRawSampler() {
  /*
    First run STD I2S at 64 kHz frame rate:
      64k * 2 slots * 16 bits = 2.048 MHz BCLK
    so the microphone is in its standard-performance clock range.
  */
  if (!initStdRawAtFrameRate(64000)) {
    return false;
  }

  delay(100);

  esp_err_t err = i2s_channel_disable(
    rx_chan
  );

  if (
    err != ESP_OK &&
    err != ESP_ERR_INVALID_STATE
  ) {
    destroyI2S();
    return false;
  }

  /*
    Then change only the STD I2S clock:
      96k * 2 * 16 = 3.072 MHz BCLK
    which is the microphone's documented ultrasonic test clock.
  */
  i2s_std_clk_config_t clk_cfg =
    I2S_STD_CLK_DEFAULT_CONFIG(
      RAW_I2S_FRAME_RATE
    );

  err =
    i2s_channel_reconfig_std_clock(
      rx_chan,
      &clk_cfg
    );

  if (err != ESP_OK) {
    destroyI2S();
    return false;
  }

  err = i2s_channel_enable(
    rx_chan
  );

  if (err != ESP_OK) {
    destroyI2S();
    return false;
  }

  delay(20);

  current_mode = MODE_RAW_STD;
  sequence_number = 0;
  return true;
}



#include <WiFi.h>
#include <time.h>
#include <sys/time.h>
#include <math.h>
#include <stdarg.h>
#include <atomic>
#include "esp_sntp.h"
#include "esp32-hal-cpu.h"
#include "CpuPowerPolicy.h"
#include "esp_system.h"

constexpr int SD_CS=43, STATUS_LED=21;
constexpr uint32_t PCM_SAMPLE_RATE_HZ=96000, PRE=48000;
constexpr uint32_t CLIP=MAX_CLIP_SECONDS*PCM_SAMPLE_RATE_HZ;
constexpr size_t PCM_BLOCK=512;
constexpr uint32_t DMA_US=42667;
constexpr uint64_t MIN_FREE_BYTES=8ULL*1024*1024;
static_assert(PERIODIC_CLIP_SECONDS<=MAX_CLIP_SECONDS,"Periodic clip exceeds RAM buffer");
static_assert(PERIODIC_SECONDS>MAX_CLIP_SECONDS,"Periodic interval must exceed clip duration");
static_assert(MAX_CLIP_SECONDS>=POST_EVENT_SECONDS+1,"Clip needs room for pretrigger");

int16_t *ring=nullptr,*clip=nullptr;
int16_t pcm[PCM_BLOCK],lut[6][256];
float fir[127],history[127],dcInput=0,dcOutput=0,dcPole;
uint16_t prevWord=0,olderWord=0;
uint32_t wordCount=0,firPos=0,ringPos=0,ringCount=0,clipCount=0;
uint32_t clipped=0,maxProcessUs=0,overBudget=0;
float hpB0,hpB1,hpB2,hpA1,hpA2,hpZ1=0,hpZ2=0;
float baselinePower=16,thresholdPower=16,sessionPeakPower=0;
uint64_t lastReadBegin=0,lastReadEnd=0;
uint64_t runFirstSampleUs=0,runSamples=0,totalSamples=0;
uint64_t gapStartUs=0,gapEndUs=0,gapTotalUs=0;
uint64_t clipStartUs=0,triggerUs=0;
uint32_t gapNumber=0,clipSequence=0,eventClips=0,periodicClips=0;
uint32_t candidatesInClip=0,clippedAtClipStart=0,captureErrors=0;
float clipPeakPower=0;
int64_t utcMinusBootUs=0;
File logFile;
char folder[96];
bool sdMounted=false,storageFault=false,micRunning=false,clockKnown=false;
bool bootTestDone=false,fatalConfig=false,sessionFailed=false;
std::atomic<bool> syncNotification{false};
time_t lastSyncEpoch=0,lastAttemptEpoch=0;
uint64_t lastSyncBootUs=0,lastAttemptBootUs=0;
bool lastSyncAttemptOK=false;
uint32_t failedSyncs=0;
int lastAttemptDate=-1;
int lastReadError=0;
CpuPowerPolicy cpuPower;
bool powerFault=false;

bool requestActiveCpu() {
  bool ok=cpuPower.requireActive([](){return getCpuFrequencyMhz();},
                                [](uint32_t mhz){return setCpuFrequencyMhz(mhz);});
  powerFault=!ok;
  if(!ok && Serial)Serial.println("POWER FAULT: active CPU frequency could not be restored; capture/storage/sync deferred.");
  return ok;
}
void updateDaytimeCpu() {
  bool safe=clockKnown && bootTestDone && !sessionFailed && !storageFault && !fatalConfig &&
            !powerFault && !micRunning && !sdMounted && !logFile && WiFi.getMode()==WIFI_OFF && !Serial;
  if(!cpuPower.updateIdle(safe,[](){return getCpuFrequencyMhz();},
                              [](uint32_t mhz){return setCpuFrequencyMhz(mhz);})) {
    // A refused idle reduction must not prevent recording at the active clock.
    requestActiveCpu();
  }
}

void led(bool on){digitalWrite(STATUS_LED,on?LOW:HIGH);}
void pattern(unsigned pulses,unsigned period) {
  uint32_t t=millis()%period;led(t<pulses*250 && t%250<100);
}
void showFault(){led(millis()%200<100);}
void printStatus() {
  if(!Serial || micRunning)return;
  Serial.println("\nXIAO overnight v1.0.2 candidate STATUS (credentials are not printed)");
#if defined(ARDUINO_USB_CDC_ON_BOOT)
  Serial.printf("USB_CDC_ON_BOOT=%d\n",ARDUINO_USB_CDC_ON_BOOT);
#endif
  Serial.printf("CPU MHz=%u active=%u idle_target=%u daytime_reduction=%d transitions=%u transition_failures=%u power_fault=%d\n",
                getCpuFrequencyMhz(),cpuPower.activeMHz(),cpuPower.idleMHz(),cpuPower.enabled(),cpuPower.attempts(),cpuPower.failures(),powerFault);
  Serial.printf("PSRAM total=%u free=%u ring_allocated=%d clip_allocated=%d\n",(unsigned)ESP.getPsramSize(),(unsigned)ESP.getFreePsram(),ring!=nullptr,clip!=nullptr);
  bool missingName=!strcmp(WIFI_SSID,"YOUR_WIFI_NAME") || !strlen(WIFI_SSID);
  bool missingPassword=!strcmp(WIFI_PASSWORD,"YOUR_WIFI_PASSWORD");
  Serial.printf("SSID_needs_edit=%d PASSWORD_needs_edit=%d config_fault=%d\n",missingName,missingPassword,fatalConfig);
  Serial.printf("Clock_synced_this_boot=%d last_sync_attempt_ok=%d failed_sync_attempts=%u WiFi_status=%d\n",clockKnown,lastSyncAttemptOK,(unsigned)failedSyncs,(int)WiFi.status());
  Serial.printf("Startup_test_done=%d SD_mounted=%d storage_fault=%d session_failed=%d\n",bootTestDone,sdMounted,storageFault,sessionFailed);
  if(fatalConfig) {
    if(missingName || missingPassword)Serial.println("CONFIG FAULT: replace WiFi placeholders in sketch and upload again.");
    if(!ring || !clip)Serial.println("CONFIG FAULT: PSRAM allocation failed. Select Tools > PSRAM > OPI PSRAM and upload again.");
    if(!missingName && !missingPassword && ring && clip)Serial.println("CONFIG FAULT: check latitude, longitude and maximum clip settings.");
  }
  Serial.println("Send s for status while idle, synchronising or waiting after a fault.");
}
void serviceSerial() {
  if(micRunning)return;
  static bool wasConnected=false;
  static uint32_t lastPrint=0;
  bool connected=bool(Serial),request=false;
  while(Serial.available()){char c=Serial.read();if(c=='s'||c=='S'||c=='?')request=true;}
  bool repeatFault=fatalConfig && uint32_t(millis()-lastPrint)>=5000;
  if(connected && (!wasConnected || request || repeatFault)){printStatus();lastPrint=millis();}
  wasConnected=connected;
}
void timedWait(uint32_t ms,bool error) {
  uint32_t start=millis();while(uint32_t(millis()-start)<ms){serviceSerial();if(error)showFault();else pattern(4,2000);delay(25);}
}
void __attribute__((format(printf,1,2))) logLine(const char *fmt,...) {
  // NEVER call during microphone acquisition; log writes can contaminate audio.
  if(micRunning){storageFault=true;return;}
  char line[512];va_list ap;va_start(ap,fmt);vsnprintf(line,sizeof(line),fmt,ap);va_end(ap);
  if(Serial)Serial.println(line);
  if(logFile){size_t n=strlen(line);if(logFile.write((const uint8_t*)line,n)!=n || logFile.write((uint8_t)'\n')!=1)storageFault=true;}
}
void stopMic(){trackOverflows=false;destroyI2S();micRunning=false;}
void utcText(time_t t,char *out,size_t n){struct tm v;gmtime_r(&t,&v);strftime(out,n,"%Y-%m-%dT%H:%M:%SZ",&v);}
void localText(time_t t,char *out,size_t n){struct tm v;localtime_r(&t,&v);strftime(out,n,"%Y-%m-%d %H:%M:%S %Z",&v);}
int dateKey(time_t t){struct tm v;localtime_r(&t,&v);return (v.tm_year+1900)*1000+v.tm_yday;}
int64_t utcUs(uint64_t bootUs){return utcMinusBootUs+(int64_t)bootUs;}
void anchorClock(){struct timeval tv;gettimeofday(&tv,nullptr);utcMinusBootUs=int64_t(tv.tv_sec)*1000000+tv.tv_usec-esp_timer_get_time();}
const char *resetReasonName() {
  switch(esp_reset_reason()) {
    case ESP_RST_POWERON:return "POWER_ON";
    case ESP_RST_EXT:return "EXTERNAL";
    case ESP_RST_SW:return "SOFTWARE";
    case ESP_RST_PANIC:return "PANIC";
    case ESP_RST_INT_WDT:return "INTERRUPT_WATCHDOG";
    case ESP_RST_TASK_WDT:return "TASK_WATCHDOG";
    case ESP_RST_WDT:return "WATCHDOG";
    case ESP_RST_DEEPSLEEP:return "DEEP_SLEEP";
    case ESP_RST_BROWNOUT:return "BROWNOUT";
    default:return "OTHER";
  }
}
void timeAvailable(struct timeval *){syncNotification.store(true);}
bool syncClock() {
  if(!requestActiveCpu()){lastSyncAttemptOK=false;failedSyncs++;lastAttemptBootUs=esp_timer_get_time();return false;}
  // Only while microphone stopped and SD unmounted. Never print credentials.
  lastAttemptBootUs=esp_timer_get_time();syncNotification.store(false);
  WiFi.mode(WIFI_STA);WiFi.setAutoReconnect(false);WiFi.begin(WIFI_SSID,WIFI_PASSWORD);
  uint32_t start=millis();
  while(WiFi.status()!=WL_CONNECTED && uint32_t(millis()-start)<20000){serviceSerial();pattern(4,2000);delay(50);}
  if(WiFi.status()==WL_CONNECTED) {
    sntp_set_time_sync_notification_cb(timeAvailable);
    // configTzTime restarts SNTP so each attempt requests a fresh update.
    configTzTime(NZ_TIMEZONE,"pool.ntp.org","time.cloudflare.com","time.google.com");
    start=millis();while(!syncNotification.load() && uint32_t(millis()-start)<15000){serviceSerial();pattern(4,2000);delay(50);}
  }
  esp_sntp_stop();
  WiFi.disconnect(true,false);WiFi.mode(WIFI_OFF);delay(100);
  time_t now=time(nullptr);
  lastSyncAttemptOK=syncNotification.load() && now>1704067200;
  if(lastSyncAttemptOK){clockKnown=true;lastSyncEpoch=now;lastSyncBootUs=esp_timer_get_time();anchorClock();}
  else failedSyncs++;
  lastAttemptEpoch=clockKnown?now:0;
  if(clockKnown)lastAttemptDate=dateKey(now);
  return lastSyncAttemptOK;
}

// NOAA fractional-year approximation. Associate solar UTC hours with the
// selected NZ calendar date using local noon (avoids a UTC-date rollover bug).
bool sunTimes(time_t localDayAnchor,time_t &rise,time_t &set) {
  struct tm d;localtime_r(&localDayAnchor,&d);int year=d.tm_year+1900;
  int days=(year%4==0 && (year%100!=0 || year%400==0))?366:365;
  double g=2*M_PI*d.tm_yday/days;
  double eq=229.18*(0.000075+0.001868*cos(g)-0.032077*sin(g)-0.014615*cos(2*g)-0.040849*sin(2*g));
  double dec=0.006918-0.399912*cos(g)+0.070257*sin(g)-0.006758*cos(2*g)+0.000907*sin(2*g)-0.002697*cos(3*g)+0.00148*sin(3*g);
  double lat=SITE_LATITUDE*M_PI/180;
  double h=cos(90.833*M_PI/180)/(cos(lat)*cos(dec))-tan(lat)*tan(dec);
  if(h< -1 || h>1)return false;
  double ha=acos(h)*180/M_PI;
  d.tm_hour=12;d.tm_min=d.tm_sec=0;d.tm_isdst=-1;time_t noon=mktime(&d);
  time_t utcMidnight=(noon/86400)*86400;
  rise=utcMidnight+(time_t)llround((720-4*(SITE_LONGITUDE+ha)-eq)*60);
  set=utcMidnight+(time_t)llround((720-4*(SITE_LONGITUDE-ha)-eq)*60);
  while(rise<noon-43200)rise+=86400;while(rise>noon+43200)rise-=86400;
  while(set<noon-43200)set+=86400;while(set>noon+43200)set-=86400;
  return rise<set;
}
time_t shiftedLocalNoon(time_t now,int days) {
  struct tm d;localtime_r(&now,&d);d.tm_hour=12;d.tm_min=d.tm_sec=0;d.tm_mday+=days;d.tm_isdst=-1;return mktime(&d);
}
bool nightWindow(time_t now,time_t &start,time_t &end) {
  time_t rise,set,otherRise,otherSet;
  if(!sunTimes(now,rise,set))return false;
  if(now<rise) {
    if(!sunTimes(shiftedLocalNoon(now,-1),otherRise,otherSet))return false;
    start=otherSet-START_BEFORE_SUNSET_MIN*60;end=rise;
  } else {
    if(!sunTimes(shiftedLocalNoon(now,1),otherRise,otherSet))return false;
    start=set-START_BEFORE_SUNSET_MIN*60;end=otherRise;
  }
  return end>start;
}
void buildFilters() {
  int weights[46]={};
  for(int a=0;a<16;a++) for(int b=0;b<16;b++) for(int c=0;c<16;c++) weights[a+b+c]++;
  for(int j=0;j<6;j++) for(int v=0;v<256;v++) {
    int sum=0;for(int k=0;k<8;k++) if(j*8+k<46) sum+=((v>>k)&1?1:-1)*weights[j*8+k];
    lut[j][v]=sum;
  }
  double total=0;
  for(int i=0;i<127;i++) {
    int m=i-63;double fc=43000.0/192000.0;
    double sinc=m?sin(2*M_PI*fc*m)/(M_PI*m):2*fc;
    fir[i]=sinc*(0.42-0.5*cos(2*M_PI*i/126)+0.08*cos(4*M_PI*i/126));total+=fir[i];
  }
  for(int i=0;i<127;i++)fir[i]/=total;
  dcPole=expf(-2*M_PI*100/PCM_SAMPLE_RATE_HZ);
  // RBJ second-order Butterworth high-pass, 20kHz at 96kHz.
  double w=2*M_PI*20000/PCM_SAMPLE_RATE_HZ, c=cos(w), alpha=sin(w)/sqrt(2.0), a0=1+alpha;
  hpB0=(1+c)/(2*a0);hpB1=-(1+c)/a0;hpB2=hpB0;
  hpA1=-2*c/a0;hpA2=(1-alpha)/a0;
}
void resetFilters() {
  memset(history,0,sizeof(history));firPos=0;wordCount=0;prevWord=olderWord=0;
  dcInput=dcOutput=hpZ1=hpZ2=0;
}
size_t convert(const uint8_t *raw,size_t bytes,int16_t *out) {
  size_t count=0;
  for(size_t p=0;p<bytes;p+=2) {
    uint16_t w=uint16_t(raw[p])|(uint16_t(raw[p+1])<<8);
    int sum=lut[0][w&255]+lut[1][w>>8];
    if(wordCount>=1)sum+=lut[2][prevWord&255]+lut[3][prevWord>>8];
    if(wordCount>=2)sum+=lut[4][olderWord&255]+lut[5][olderWord>>8];
    history[firPos]=sum/4096.0f;
    if(wordCount&1) {
      float f=0;int pos=firPos;
      for(int j=0;j<127;j++){f+=fir[j]*history[pos];if(--pos<0)pos=126;}
      float y=f-dcInput+dcPole*dcOutput;dcInput=f;dcOutput=y;
      float scaled=y*(8*32768.0f);
      if(scaled>32767){scaled=32767;clipped++;}
      if(scaled< -32768){scaled=-32768;clipped++;}
      out[count++]=(int16_t)lroundf(scaled);
    }
    firPos=(firPos+1)%127;olderWord=prevWord;prevWord=w;wordCount++;
  }
  return count;
}
float powerOf(const int16_t *samples,size_t n) {
  double power=0;
  for(size_t i=0;i<n;i++) {
    float x=samples[i], y=hpB0*x+hpZ1;
    hpZ1=hpB1*x-hpA1*y+hpZ2;hpZ2=hpB2*x-hpA2*y;power+=y*y;
  }
  return power/n;
}
bool readBlock() {
  size_t n=0;lastReadBegin=esp_timer_get_time();
  esp_err_t e=i2s_channel_read(rx_chan,io_buffer,sizeof(io_buffer),&n,1000);
  lastReadEnd=esp_timer_get_time();lastReadError=(int)e;
  if(e!=ESP_OK || n!=sizeof(io_buffer) || overflowCount)return false;
  uint64_t t=esp_timer_get_time();if(convert(io_buffer,n,pcm)!=PCM_BLOCK)return false;
  uint32_t us=esp_timer_get_time()-t;if(us>maxProcessUs)maxProcessUs=us;if(us>5333)overBudget++;
  return true;
}
bool startMic() {
  led(true);trackOverflows=false;
  if(!enterRawSampler()){stopMic();return false;}
  micRunning=true;resetFilters();
  for(int i=0;i<16;i++) {
    size_t n=0;if(i2s_channel_read(rx_chan,io_buffer,sizeof(io_buffer),&n,1000)!=ESP_OK || n!=sizeof(io_buffer)){stopMic();return false;}
  }
  overflowCount=0;
  for(int i=0;i<20;i++)if(!readBlock()){stopMic();return false;}
  overflowCount=0;trackOverflows=true;runSamples=0;runFirstSampleUs=0;ringPos=ringCount=0;
  return true;
}
void remember(const int16_t *p,size_t n) {
  for(size_t i=0;i<n;i++){ring[ringPos]=p[i];ringPos=(ringPos+1)%PRE;if(ringCount<PRE)ringCount++;}
}
void pretrigger() {
  clipCount=ringCount;uint32_t pos=(ringPos+PRE-ringCount)%PRE;
  for(uint32_t i=0;i<ringCount;i++){clip[i]=ring[pos];pos=(pos+1)%PRE;}
}
void put16(uint8_t *p,uint16_t x){p[0]=x;p[1]=x>>8;}
void put32(uint8_t *p,uint32_t x){for(int i=0;i<4;i++)p[i]=x>>(8*i);}

bool enoughSpace(){return SD.totalBytes()>SD.usedBytes()+MIN_FREE_BYTES;}
void logSyncState() {
  char stamp[32],attempt[32];utcText(lastSyncEpoch,stamp,sizeof(stamp));utcText(lastAttemptEpoch,attempt,sizeof(attempt));
  logLine("TIME last_sync_utc=%s last_sync_boot_us=%llu age_seconds=%lld last_attempt_utc=%s last_attempt_status=%s failed_attempts=%u",stamp,(unsigned long long)lastSyncBootUs,(long long)(time(nullptr)-lastSyncEpoch),attempt,lastSyncAttemptOK?"OK":"FAIL",(unsigned)(failedSyncs));
  logLine("TIME_MAP utc_minus_boot_us=%lld sample_timestamp_uncertainty_includes_dma_us=%u",(long long)utcMinusBootUs,(unsigned)(DMA_US));
}
bool openSession(const char *kind,time_t scheduleStart,time_t scheduleEnd) {
  if(!requestActiveCpu())return false;
  stopMic();led(true);storageFault=false;sessionFailed=false;
  if(!SD.begin(SD_CS,SPI,4000000)){SD.end();sdMounted=false;return false;}sdMounted=true;
  if(SD.cardType()==CARD_NONE || !enoughSpace()){SD.end();sdMounted=false;return false;}
  time_t now=time(nullptr);struct tm d;gmtime_r(&now,&d);char stamp[32];strftime(stamp,sizeof(stamp),"%Y%m%dT%H%M%SZ",&d);
  bool found=false;
  for(int i=0;i<1000;i++){snprintf(folder,sizeof(folder),"/%s_%s_%03d",kind,stamp,i);if(!SD.exists(folder)){found=SD.mkdir(folder);break;}}
  if(!found){SD.end();sdMounted=false;return false;}
  char path[128];snprintf(path,sizeof(path),"%s/session.txt",folder);logFile=SD.open(path,FILE_WRITE);
  if(!logFile){SD.end();sdMounted=false;return false;}
  clipped=maxProcessUs=overBudget=captureErrors=0;clipSequence=eventClips=periodicClips=0;
  gapNumber=0;gapStartUs=gapEndUs=gapTotalUs=0;totalSamples=0;sessionPeakPower=0;clipCount=0;
  anchorClock();
  logLine("POWER cpu_mhz=%u active_cpu_mhz=%u daytime_cpu_mhz=%u daytime_reduction=%d clock_switch_failures=%u",getCpuFrequencyMhz(),cpuPower.activeMHz(),cpuPower.idleMHz(),cpuPower.enabled(),cpuPower.failures());
  logLine("XIAO bat overnight pilot v1.0.2 candidate kind=%s reset_reason=%s reset_code=%d boot_us=%llu",kind,resetReasonName(),(int)esp_reset_reason(),(unsigned long long)esp_timer_get_time());
  logLine("AUDIO fs=96000 channels=1 bits=16 gain=8 cic3_decimation=16 fir_taps=127 fir_cutoff_hz=43000 sd_spi_hz=4000000");
  logLine("DETECTOR experimental_highpass_20k rms_multiplier=%.2f min_rms=%.2f window_samples=512 windows_required=1",TRIGGER_RMS_MULTIPLIER,MIN_TRIGGER_RMS);
  logLine("RECORD pretrigger_samples=%u post_event_seconds=%u max_seconds=%u periodic_seconds=%u periodic_clip_seconds=%u",(unsigned)(PRE),(unsigned)(POST_EVENT_SECONDS),(unsigned)(MAX_CLIP_SECONDS),(unsigned)(PERIODIC_SECONDS),(unsigned)(PERIODIC_CLIP_SECONDS));
  logLine("STORAGE free_bytes=%llu no_readback=1",(unsigned long long)(SD.totalBytes()-SD.usedBytes()));
  char a[40],b[40];utcText(scheduleStart,a,sizeof(a));utcText(scheduleEnd,b,sizeof(b));
  logLine("SCHEDULE latitude=%.5f longitude=%.5f start_utc=%s end_utc=%s",SITE_LATITUDE,SITE_LONGITUDE,a,b);
  localText(scheduleStart,a,sizeof(a));localText(scheduleEnd,b,sizeof(b));logLine("SCHEDULE_LOCAL start=%s end=%s",a,b);
  logSyncState();logFile.flush();return !storageFault;
}
void finishPreviousGap() {
  if(gapStartUs && gapEndUs) {
    uint64_t duration=gapEndUs-gapStartUs;gapTotalUs+=duration;
    logLine("GAP_END id=%u end_boot_us=%llu end_utc_us=%lld duration_us=%llu",(unsigned)(gapNumber),(unsigned long long)gapEndUs,(long long)utcUs(gapEndUs),(unsigned long long)duration);
    gapStartUs=gapEndUs=0;
  }
}
void noteRunEnd(const char *reason,bool valid) {
  if(!runSamples)return;
  logLine("LISTEN_SPAN first_sample_est_boot_us=%llu first_sample_est_utc_us=%lld samples=%llu sample_seconds=%.6f last_read_end_boot_us=%llu valid=%d end_reason=%s",(unsigned long long)runFirstSampleUs,(long long)utcUs(runFirstSampleUs),(unsigned long long)runSamples,double(runSamples)/PCM_SAMPLE_RATE_HZ,(unsigned long long)lastReadEnd,valid,reason);
  runSamples=0;
}
void pauseCapture(const char *reason,bool valid) {
  uint64_t bound=lastReadBegin>DMA_US?lastReadBegin-DMA_US:0;
  stopMic();finishPreviousGap();noteRunEnd(reason,valid);
  // A failed start before any resumed read leaves the existing gap open.
  if(!gapStartUs) {
    gapStartUs=bound?bound:esp_timer_get_time();gapEndUs=0;gapNumber++;
    logLine("GAP_BEGIN id=%u conservative_start_boot_us=%llu start_utc_us=%lld reason=%s",(unsigned)(gapNumber),(unsigned long long)gapStartUs,(long long)utcUs(gapStartUs),reason);
  }
}
void closeSession(const char *reason) {
  stopMic();finishPreviousGap();
  if(logFile) {
    if(gapStartUs)logLine("GAP_OPEN id=%u start_boot_us=%llu no_resume_before_session_end=1",(unsigned)(gapNumber),(unsigned long long)gapStartUs);
    logLine("SUMMARY listened_samples=%llu listened_sample_seconds=%.6f event_clips=%u periodic_clips=%u clipped_samples=%u max_conversion_us=%u conversion_blocks_over_5333us=%u capture_errors=%u completed_gap_bound_seconds=%.6f",(unsigned long long)totalSamples,double(totalSamples)/PCM_SAMPLE_RATE_HZ,(unsigned)(eventClips),(unsigned)(periodicClips),(unsigned)(clipped),(unsigned)(maxProcessUs),(unsigned)(overBudget),(unsigned)(captureErrors),double(gapTotalUs)/1e6);
    logLine("SESSION_END reason=%s storage_fault=%d boot_us=%llu utc_us=%lld",reason,storageFault,(unsigned long long)esp_timer_get_time(),(long long)utcUs(esp_timer_get_time()));
    logFile.flush();logFile.close();
  }
  if(sdMounted)SD.end();sdMounted=false;
}
bool saveClip(const char *kind,const char *reason,bool valid) {
  // Called only after microphone stops. No second raw file or full SD readback.
  led(true);if(!clipCount)return true;
  if(!enoughSpace()){logLine("ERROR insufficient_free_space");storageFault=true;return false;}
  time_t clipEpoch=(time_t)(utcUs(clipStartUs)/1000000);struct tm d;gmtime_r(&clipEpoch,&d);
  char stamp[32],path[160];strftime(stamp,sizeof(stamp),"%Y%m%dT%H%M%SZ",&d);
  snprintf(path,sizeof(path),"%s/%s_%s_%05u.wav",folder,kind,stamp,(unsigned)clipSequence++);
  if(SD.exists(path)){logLine("ERROR filename_already_exists path=%s",path);storageFault=true;return false;}
  uint32_t bytes=clipCount*2;uint8_t h[44]={};
  memcpy(h,"RIFF",4);put32(h+4,36+bytes);memcpy(h+8,"WAVEfmt ",8);put32(h+16,16);
  put16(h+20,1);put16(h+22,1);put32(h+24,PCM_SAMPLE_RATE_HZ);put32(h+28,PCM_SAMPLE_RATE_HZ*2);
  put16(h+32,2);put16(h+34,16);memcpy(h+36,"data",4);put32(h+40,bytes);
  uint64_t start=esp_timer_get_time();File f=SD.open(path,FILE_WRITE);bool ok=bool(f);
  uint32_t hash=2166136261UL,written=0;
  if(f) {
    ok=f.write(h,44)==44;const uint8_t *p=(const uint8_t*)clip;
    while(ok && written<bytes) {
      size_t n=min(size_t(8192),size_t(bytes-written));
      for(size_t i=0;i<n;i++)hash=(hash^p[written+i])*16777619UL;
      size_t got=f.write(p+written,n);written+=got;ok=got==n;delay(1);
    }
    f.flush();ok=ok && f.size()==bytes+44;f.close();
  }
  logLine("FILE path=%s samples=%u payload_bytes_written=%u fnv1a=%08lx write_status=%s capture_valid=%d readback=NOT_DONE",path,(unsigned)(clipCount),(unsigned)(written),(unsigned long)hash,ok?"OK":"FAIL",valid);
  logLine("CLIP kind=%s reason=%s start_est_utc_us=%lld start_est_boot_us=%llu duration_seconds=%.6f trigger_read_end_utc_us=%lld candidates=%u peak_hp_rms=%.3f threshold_rms=%.3f clipped_since_trigger=%u save_us=%llu",kind,reason,(long long)utcUs(clipStartUs),(unsigned long long)clipStartUs,double(clipCount)/PCM_SAMPLE_RATE_HZ,(long long)(triggerUs?utcUs(triggerUs):0),(unsigned)(candidatesInClip),sqrtf(clipPeakPower),sqrtf(thresholdPower),(unsigned)(clipped-clippedAtClipStart),(unsigned long long)(esp_timer_get_time()-start));
  if(!strcmp(kind,"event"))eventClips++;else periodicClips++;
  if(!ok)storageFault=true;logFile.flush();return ok && !storageFault;
}
void acceptRead() {
  if(!runSamples) {
    runFirstSampleUs=lastReadEnd-(uint64_t)PCM_BLOCK*1000000/PCM_SAMPLE_RATE_HZ;
    if(gapStartUs && !gapEndUs)gapEndUs=lastReadEnd;
  }
  runSamples+=PCM_BLOCK;totalSamples+=PCM_BLOCK;
}
int compareFloat(const void *a,const void *b){float x=*(const float*)a,y=*(const float*)b;return (x>y)-(x<y);}
bool calibrate() {
  static float powers[563]; // Median avoids a few transient sounds dominating calibration.
  logLine("CALIBRATION begin_boot_us=%llu blocks=563 median=1",(unsigned long long)esp_timer_get_time());logFile.flush();
  if(!startMic()){logLine("ERROR calibration_microphone_start");return false;}
  for(int i=0;i<563;i++) {
    if(!readBlock()){stopMic();logLine("ERROR calibration_read code=%d overflows=%u",lastReadError,(unsigned)((unsigned)overflowCount));return false;}
    powers[i]=powerOf(pcm,PCM_BLOCK);
  }
  stopMic();qsort(powers,563,sizeof(float),compareFloat);baselinePower=fmaxf(powers[281],1.0f);
  thresholdPower=fmaxf(MIN_TRIGGER_RMS*MIN_TRIGGER_RMS,baselinePower*TRIGGER_RMS_MULTIPLIER*TRIGGER_RMS_MULTIPLIER);
  logLine("CALIBRATION end_boot_us=%llu median_hp_rms=%.3f threshold_rms=%.3f",(unsigned long long)esp_timer_get_time(),sqrtf(baselinePower),sqrtf(thresholdPower));logFile.flush();
  return !storageFault;
}
bool startupRecording() {
  if(!startMic()){logLine("ERROR startup_microphone_start");return false;}
  clipCount=0;clipPeakPower=0;candidatesInClip=0;triggerUs=0;clippedAtClipStart=clipped;
  uint32_t wanted=10*PCM_SAMPLE_RATE_HZ;
  while(clipCount<wanted) {
    pattern(2,2000);
    if(!readBlock()){pauseCapture("startup_read_error",false);logLine("ERROR startup_read code=%d overflows=%u",lastReadError,(unsigned)((unsigned)overflowCount));return false;}
    acceptRead();if(!clipCount)clipStartUs=runFirstSampleUs;
    size_t n=min(PCM_BLOCK,size_t(wanted-clipCount));memcpy(clip+clipCount,pcm,n*2);clipCount+=n;
    float p=powerOf(pcm,n);if(p>clipPeakPower)clipPeakPower=p;
  }
  stopMic();noteRunEnd("startup_complete",true);
  return saveClip("startup","boot_check",true);
}
bool monitorNight(time_t sunrise) {
  if(!calibrate())return false;
  logLine("MONITOR_START utc_us=%lld",(long long)utcUs(esp_timer_get_time()));logFile.flush();
  if(!startMic()){logLine("ERROR monitor_microphone_start");return false;}
  bool recording=false,periodic=false;
  uint64_t nextPeriodicUs=esp_timer_get_time(),lastCandidateSample=0;
  while(time(nullptr)<sunrise) {
    pattern(recording?2:1,2000);
    if(!readBlock()) {
      captureErrors++;pauseCapture("read_error",false);
      logLine("ERROR audio_read code=%d overflows=%u",lastReadError,(unsigned)((unsigned)overflowCount));
      if(recording && clipCount)saveClip(periodic?"periodic":"event","read_error_partial",false);
      return false;
    }
    acceptRead();float p=powerOf(pcm,PCM_BLOCK);if(p>sessionPeakPower)sessionPeakPower=p;
    bool candidate=p>thresholdPower;
    if(recording) {
      size_t n=min(PCM_BLOCK,size_t(CLIP-clipCount));memcpy(clip+clipCount,pcm,n*2);clipCount+=n;
      if(p>clipPeakPower)clipPeakPower=p;
      if(candidate){lastCandidateSample=runSamples;candidatesInClip++;}
    }
    remember(pcm,PCM_BLOCK);
    if(!recording) {
      bool due=lastReadEnd>=nextPeriodicUs;
      if(due || candidate) {
        recording=true;periodic=due;pretrigger();
        clipStartUs=runFirstSampleUs+(runSamples-clipCount)*1000000/PCM_SAMPLE_RATE_HZ;
        triggerUs=candidate?lastReadEnd:0;lastCandidateSample=runSamples;
        clipPeakPower=p;candidatesInClip=candidate?1:0;clippedAtClipStart=clipped;
        if(due) {do{nextPeriodicUs+=(uint64_t)PERIODIC_SECONDS*1000000;}while(nextPeriodicUs<=lastReadEnd);}
      } else {
        // Slow background tracking (~96s time constant), only below threshold
        // and outside saved clips. No adaptation during strong events.
        baselinePower+=0.00005556f*(p-baselinePower);
        thresholdPower=fmaxf(MIN_TRIGGER_RMS*MIN_TRIGGER_RMS,baselinePower*TRIGGER_RMS_MULTIPLIER*TRIGGER_RMS_MULTIPLIER);
      }
    }
    bool maxed=clipCount>=CLIP;
    bool periodicDone=periodic && clipCount>=PERIODIC_CLIP_SECONDS*PCM_SAMPLE_RATE_HZ;
    bool tailDone=!periodic && runSamples-lastCandidateSample>=POST_EVENT_SECONDS*PCM_SAMPLE_RATE_HZ;
    if(recording && (maxed || periodicDone || tailDone)) {
      const char *why=periodic?"scheduled":(maxed?"max_duration":"post_event_tail");
      // Truncate a partial final block if a non-default periodic length is used.
      if(periodic && clipCount>PERIODIC_CLIP_SECONDS*PCM_SAMPLE_RATE_HZ)clipCount=PERIODIC_CLIP_SECONDS*PCM_SAMPLE_RATE_HZ;
      pauseCapture("save_wav",true);
      logLine("BACKGROUND hp_rms=%.3f threshold_rms=%.3f session_peak_hp_rms=%.3f",sqrtf(baselinePower),sqrtf(thresholdPower),sqrtf(sessionPeakPower));
      if(!saveClip(periodic?"periodic":"event",why,true))return false;
      recording=false;clipCount=0;
      if(time(nullptr)>=sunrise)break;
      if(!startMic()){logLine("ERROR restart_after_save");return false;}
    }
  }
  stopMic();finishPreviousGap();noteRunEnd("sunrise",true);
  if(recording && clipCount)if(!saveClip(periodic?"periodic":"event","sunrise_partial",true))return false;
  logLine("MONITOR_END sunrise_reached=1 utc_us=%lld",(long long)utcUs(esp_timer_get_time()));
  return !storageFault;
}
void printSchedule(time_t a,time_t b) {
  if(!Serial)return;
  char x[40],y[40];localText(a,x,sizeof(x));localText(b,y,sizeof(y));
  Serial.printf("Scheduled listening: %s until %s\n",x,y);
}
void setup() {
  cpuPower.begin(getCpuFrequencyMhz(),DAYTIME_CPU_MHZ,ENABLE_DAYTIME_CPU_REDUCTION);
  Serial.begin(115200);pinMode(STATUS_LED,OUTPUT);led(false);
  pinMode(41,OUTPUT);digitalWrite(41,HIGH);pinMode(SD_CS,OUTPUT);digitalWrite(SD_CS,HIGH);
  SPI.begin(7,8,9,SD_CS);setenv("TZ",NZ_TIMEZONE,1);tzset();
  WiFi.persistent(false);WiFi.mode(WIFI_OFF);
  ring=(int16_t*)heap_caps_malloc(PRE*2,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
  clip=(int16_t*)heap_caps_malloc(CLIP*2,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
  fatalConfig=!ring || !clip || !strcmp(WIFI_SSID,"YOUR_WIFI_NAME") || !strcmp(WIFI_PASSWORD,"YOUR_WIFI_PASSWORD") || strlen(WIFI_SSID)==0 ||
              SITE_LATITUDE< -65 || SITE_LATITUDE>65 || SITE_LONGITUDE< -180 || SITE_LONGITUDE>180 || MAX_CLIP_SECONDS<10;
  buildFilters();delay(1500);
  if(fatalConfig && Serial)Serial.println("CONFIG FAULT: enter WiFi SSID and enable OPI PSRAM; check settings.");
}
void loop() {
  if((Serial || powerFault) && !requestActiveCpu()){showFault();delay(50);return;}
  serviceSerial();
  if(fatalConfig){showFault();delay(25);return;}
  if(!clockKnown) {
    if(!syncClock()){if(Serial)Serial.println("TIME FAULT: WiFi/NTP failed; retry in30s. No scheduled recording without fresh time.");timedWait(30000,true);return;}
  }
  time_t now=time(nullptr),start=0,end=0;
  if(!nightWindow(now,start,end)){if(Serial)Serial.println("FAULT: solar schedule calculation");timedWait(30000,true);return;}
  if(!bootTestDone) {
    printSchedule(start,end);
    bool ok=openSession("startup",start,end);
    if(ok) {
      // Preserve the proven initial 32kHz PDM -> raw sampler startup path.
      ok=enterAudible();stopMic();
      if(ok)ok=startupRecording();
    }
    closeSession(ok?"startup_check_complete":"startup_check_failed");
    if(!ok || storageFault){if(Serial)Serial.println("STARTUP FAULT: SD/microphone. Retry in30s.");timedWait(30000,true);return;}
    bootTestDone=true;
    now=time(nullptr);if(!nightWindow(now,start,end)){timedWait(30000,true);return;}
  }
  if(now>=start && now<end) {
    bool ok=openSession("night",start,end);
    if(ok)ok=monitorNight(end);
    closeSession(ok?"sunrise":"error_retry_pending");
    sessionFailed=!ok || storageFault;
    if(sessionFailed){if(Serial)Serial.println("NIGHT FAULT: restarting session in30s; inspect logs.");timedWait(30000,true);}
    return;
  }
  // Daytime: SD is unmounted and untouched. WiFi alone may run at noon.
  struct tm local;localtime_r(&now,&local);
  bool newDay=dateKey(now)!=lastAttemptDate;
  bool retryFailed=!lastSyncAttemptOK && uint64_t(esp_timer_get_time()-lastAttemptBootUs)>=900ULL*1000000;
  if(local.tm_hour>=12 && (newDay || retryFailed)) {
    syncClock(); // Running clock remains usable if this daily attempt fails.
    now=time(nullptr);if(nightWindow(now,start,end))printSchedule(start,end);
  }
  if(sessionFailed || powerFault)showFault();else pattern(3,3000);
  updateDaytimeCpu();
  delay(50);
}
