// NZRT_JOURNAL_V2
#include "WildlifeJournal.h"
/*
 * NZRT microphone / genuine MeshCore repeater coexistence probe.
 *
 * PDM bitstream acquisition on ESP32-S3 in legacy Arduino-ESP32 2.x I2S
 * (IDF 4.4) so it can compile with MeshCore v1.18.0's PlatformIO platform.
 * The independent, validated Arduino-ESP32 3.3.12 I2S_STD sampler remains
 * in PR #10. This port MUST be validated acoustically and on hardware.
 *
 * CLK D0/GPIO1, DATA D1/GPIO2. Breakout SEL grounded by populated R1.
 * GPIO4/D3 is used as unwired WS, avoiding MeshCore I2C D4/D5.
 */
#include "WildlifeMic.h"
#include "WildlifeML.h"
#include "WildlifeDetector.h"
#include "WildlifeTime.h"
#include <SPIFFS.h>  // same flash filesystem used by upstream MeshCore repeater
#include <driver/i2s.h>
#include <esp_timer.h>
#include <esp_heap_caps.h>
#include <esp_system.h>
#include <stdio.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>

namespace WildlifeDetector {uint32_t optionalClipHolds(); void blockTiming(uint32_t&,uint32_t&,uint32_t&);}
namespace WildlifeML {void testAudioIdle();unsigned compareStage();}

namespace WildlifeMic {
namespace {
constexpr i2s_port_t PORT = I2S_NUM_0;
constexpr int CLK = 1, DATA = 2, DUMMY_WS = 4;
constexpr size_t BUFFER_BYTES = 2048;
constexpr uint32_t REPORT_MS = 60000;
portMUX_TYPE statsLock = portMUX_INITIALIZER_UNLOCKED;
QueueHandle_t eventQueue = nullptr;
TaskHandle_t captureTask = nullptr;
TaskHandle_t dspTaskHandle = nullptr;
QueueHandle_t dspQueue = nullptr;
// Field pilot auto-starts DSP after MeshCore/microphone initialization.
// The existing nzrt dsp on/off commands remain available for diagnostics.
volatile bool dspEnabledRequest = false;
volatile bool captureEnabledRequest = true;
volatile bool captureRunning = false;
volatile bool dayStandby = false;
constexpr const char* BUILD_ID = "NZRT-J4-PASS-1";
uint32_t sessionId = 0;
uint32_t journalWriteFailures = 0;
volatile uint32_t dspStartUptimeMs = 0;
volatile uint32_t dspRunNumber = 0;

constexpr uint8_t EXT_BLOCKS=48, INTERNAL_BLOCKS=8;
uint8_t poolCapacity=0;
QueueHandle_t freeSlots=nullptr;
struct RawBlock {
  uint32_t seq;
  uint32_t n;
  uint32_t captureEndUptimeMs;
  uint32_t words[BUFFER_BYTES / sizeof(uint32_t)];
};


// Slots move free -> reader -> ready -> DSP -> free. Only one-byte
// indices cross the RTOS queue locks; PCM/I2S work uses internal task RAM.
RawBlock* pool=nullptr;
void releasePool(){
  if(dspQueue)vQueueDelete(dspQueue);
  if(freeSlots)vQueueDelete(freeSlots);
  free(pool);pool=nullptr;dspQueue=freeSlots=nullptr;poolCapacity=0;
}
bool allocatePool(uint8_t capacity,uint32_t caps){
  pool=static_cast<RawBlock*>(heap_caps_malloc(capacity*sizeof(RawBlock),caps|MALLOC_CAP_8BIT));
  if(pool){freeSlots=xQueueCreate(capacity,1);dspQueue=xQueueCreate(capacity,1);}
  if(!pool||!freeSlots||!dspQueue){releasePool();return false;}
  poolCapacity=capacity;
  for(uint8_t i=0;i<capacity;++i)xQueueSend(freeSlots,&i,0);
  return true;
}
bool enqueueBlock(const RawBlock& packet){
  uint8_t slot;
  if(xQueueReceive(freeSlots,&slot,0)!=pdTRUE)return false;
  memcpy(&pool[slot],&packet,sizeof(packet));
  if(xQueueSend(dspQueue,&slot,0)==pdTRUE)return true;
  xQueueSend(freeSlots,&slot,0);return false;
}
void drainBlocks(){
  uint8_t slot;
  while(xQueueReceive(dspQueue,&slot,0)==pdTRUE)xQueueSend(freeSlots,&slot,0);
}
struct Stats {
  uint64_t bytes = 0;
  uint64_t ones = 0;
  uint32_t fullReads = 0;
  uint32_t shortReads = 0;
  uint32_t readErrors = 0;
  uint32_t rxQueueOverflows = 0;
  uint32_t maxReadUs = 0;
  uint32_t maxProcessUs = 0;
  uint32_t processOverBudget = 0;
  uint32_t dspQueueDrops = 0;
  uint32_t dspStreamResets = 0;
  uint32_t dspBlocksProcessed = 0;
  uint32_t maxQueueDepth = 0;
  uint32_t decodeUs=0,analysisUs=0,scoreUs=0,peakDepth=0,peakDspUs=0;


};
Stats stats;
bool started = false;

// The capture reader is high-priority and must never perform FIR/PCM work.
// A bounded queue decouples radio/USB servicing from slower audio analysis.
void readerTask(void*) {
  RawBlock pkt = {};
  uint32_t seq = 0,emptyReads=0;
  for (;;) {
    // Only the reader task owns I2S start/stop, so the scheduler cannot race
    // an in-progress i2s_read() from another core. LoRa keeps running.
    if(!captureEnabledRequest) {
      if(captureRunning) {
        esp_err_t rc=i2s_stop(PORT);
        if(rc!=ESP_OK) Serial.printf("NZRT DAY I2S_STOP_FAILED error=%d\n",(int)rc);
        else captureRunning=false;
      }
      emptyReads=0;
      vTaskDelay(pdMS_TO_TICKS(100));
      continue;
    }
    if(!captureRunning) {
      esp_err_t rc=i2s_start(PORT);
      if(rc!=ESP_OK) {
        Serial.printf("NZRT DAY I2S_START_FAILED error=%d retry=2s\n",(int)rc);
        vTaskDelay(pdMS_TO_TICKS(2000));
        continue;
      }
      captureRunning=true;
      Serial.println("NZRT DAY I2S=RESTARTED");
    }
    size_t n = 0;
    int64_t before = esp_timer_get_time();
    esp_err_t status = i2s_read(PORT, pkt.words, sizeof(pkt.words), &n,
                                pdMS_TO_TICKS(1000));
    uint32_t elapsed = static_cast<uint32_t>(esp_timer_get_time() - before);
    uint32_t overflowDelta=0;
    i2s_event_t event;
    while(eventQueue && xQueueReceive(eventQueue, &event, 0) == pdTRUE)
      if(event.type == I2S_EVENT_RX_Q_OVF) ++overflowDelta;
    uint32_t ones = 0;
    // Count every read attempt. Dropped/partial reads must break PCM continuity.
    ++seq;
    if(overflowDelta)++seq;
    if(status == ESP_OK) {
      for(size_t i=0; i<n/sizeof(uint32_t); ++i)
        ones += static_cast<uint32_t>(__builtin_popcount(pkt.words[i]));
      pkt.seq = seq;
      pkt.n = static_cast<uint32_t>(n);
      pkt.captureEndUptimeMs=millis();
    }
    uint32_t queueDrop=0, queueDepth=0;
    if(status == ESP_OK && n==sizeof(pkt.words) && dspEnabledRequest) {
      // Non-blocking. Prefer dropping an analysis block to missing I2S DMA.
      if(!enqueueBlock(pkt))
        ++queueDrop;
      else
        queueDepth = static_cast<uint32_t>(uxQueueMessagesWaiting(dspQueue));
    }
    portENTER_CRITICAL(&statsLock);
    if(queueDrop)queueDepth=poolCapacity;
    if(queueDepth>stats.peakDepth)stats.peakDepth=queueDepth;
    stats.bytes += n;
    stats.ones += ones;
    stats.rxQueueOverflows += overflowDelta;
    stats.dspQueueDrops += queueDrop;
    if (queueDepth > stats.maxQueueDepth) stats.maxQueueDepth=queueDepth;
    if(status != ESP_OK) ++stats.readErrors;
    else if(n!=sizeof(pkt.words)) ++stats.shortReads;
    else ++stats.fullReads;
    if(elapsed > stats.maxReadUs) stats.maxReadUs=elapsed;
    portEXIT_CRITICAL(&statsLock);
    if(status==ESP_OK && n)emptyReads=0;
    else if(++emptyReads>=3) {
      emptyReads=0;
      ++seq;
      if(i2s_stop(PORT)==ESP_OK)captureRunning=false;
      Serial.println("NZRT MIC recovery=empty_reads");
      vTaskDelay(pdMS_TO_TICKS(100));
    }
    if(status != ESP_OK) vTaskDelay(pdMS_TO_TICKS(2));
  }
}
void dspTask(void*) {
  RawBlock pkt;
  uint32_t prevSeq=0, processed=0, contextRun=0;
  bool running=false;
  for(;;) {
    bool requested=dspEnabledRequest;
    if(requested!=running || (requested && contextRun!=dspRunNumber)) {
      running=requested;
      contextRun=dspRunNumber;
      WildlifeDetector::reset(contextRun,dspStartUptimeMs);
      prevSeq=0;
      // Only the DSP task resets its FIFO/algorithm state.
      drainBlocks();
    }
    if(!running) {vTaskDelay(pdMS_TO_TICKS(25));continue;}
    uint8_t slot;
    if(xQueueReceive(dspQueue,&slot,pdMS_TO_TICKS(100)) != pdTRUE) {
      WildlifeML::testAudioIdle();
      vTaskDelay(1);
      continue;
    }
    memcpy(&pkt,&pool[slot],sizeof(pkt));
    xQueueSend(freeSlots,&slot,0);
    if(!dspEnabledRequest) continue;
    // Detect gaps in the PDM byte stream and re-establish the noise baseline.
    if(prevSeq && pkt.seq!=prevSeq+1) {
      WildlifeDetector::onInputGap(pkt.seq-prevSeq-1);
      portENTER_CRITICAL(&statsLock);
      ++stats.dspStreamResets;
      portEXIT_CRITICAL(&statsLock);
    }
    prevSeq=pkt.seq;
    int64_t before=esp_timer_get_time();
    WildlifeDetector::consume(reinterpret_cast<const uint8_t*>(pkt.words),pkt.n,pkt.captureEndUptimeMs);
    uint32_t elapsed=static_cast<uint32_t>(esp_timer_get_time()-before);
    uint32_t decode=0,analysis=0,score=0;
    WildlifeDetector::blockTiming(decode,analysis,score);
    portENTER_CRITICAL(&statsLock);
    stats.scoreUs+=score;
    stats.decodeUs+=decode;stats.analysisUs+=analysis;
    if(elapsed>stats.peakDspUs)stats.peakDspUs=elapsed;
    if(elapsed>stats.maxProcessUs)stats.maxProcessUs=elapsed;
    if(pkt.n && elapsed>(pkt.n*1000000UL/384000UL))++stats.processOverBudget;
    ++stats.dspBlocksProcessed;
    portEXIT_CRITICAL(&statsLock);
    // Give IDLE0 / low-priority Wi-Fi housekeeping guaranteed CPU time.
    // Yield to core0 idle/Wi-Fi without consuming ~5% of DSP time.
    if((++processed & 15U)==0) vTaskDelay(1);
  }
}
// One format for USB and retained flash. Compile-time printf type checking.
void formatEvent(char* line,size_t size,const WildlifeDetector::Event& ev) {
  const auto& f=ev.features;
  uint32_t startUtc=WildlifeTime::epochForUptime(ev.start_uptime_ms);
  uint32_t endUtc=WildlifeTime::epochForUptime(ev.end_uptime_ms);
  snprintf(line,size,
    "NZRT CANDIDATE session=%08lX run=%lu seq=%lu from_ms=%lu to_ms=%lu utc_start=%lu utc_end=%lu time_source=%s peak=%.2fx score_version=%s score=%u class=%s shadow=1 pulses=%lu short_pulses=%lu pulse_mean_ms=%.2f pulse_max_ms=%.2f gap_mean_ms=%.2f freq_mean_khz=%.2f freq_min_khz=%.2f freq_max_khz=%.2f narrow_fraction=%.3f duty=%.3f harmonic_fraction=%.3f ended_reason=%u clip_request=%s clip_owner_seq=%lu bench=%d first_pass=%s pass_shadow=%s pass_shadow_hit=%u unverified=1\n",
    (unsigned long)sessionId,(unsigned long)ev.run,(unsigned long)ev.seq,
    (unsigned long)ev.start_ms,(unsigned long)ev.end_ms,
    (unsigned long)startUtc,(unsigned long)endUtc,WildlifeTime::source(),
    ev.peak_ratio,WildlifeScoring::VERSION,(unsigned)f.score,
    f.bat_like?"bat_like":"uncertain",(unsigned long)f.pulses,
    (unsigned long)f.short_pulses,f.pulse_mean_ms,f.pulse_max_ms,f.gap_mean_ms,
    f.freq_mean_khz,f.freq_min_khz,f.freq_max_khz,
    f.voiced_frames?float(f.narrow_frames)/f.voiced_frames:0.0f,
    f.duty,f.harmonic_fraction,(unsigned)ev.ended_reason,ev.clipRequest,(unsigned long)ev.clipOwnerSeq,ev.bench,WildlifeDetector::passName(ev.passConfig&3),
    (ev.passConfig>>2)?WildlifeDetector::passName((ev.passConfig>>2)-1):"off",unsigned(ev.shadowMatched));
}
// Main loop owns both producers and HTTP acknowledgements.
constexpr size_t LIVE_CAPACITY=64;
WildlifeDetector::Event liveEvents[LIVE_CAPACITY];
size_t liveHead=0,liveCount=0;
uint32_t liveDropped=0,liveAcked=0;
char liveHealth[256]={};
void queueLive(const WildlifeDetector::Event& ev) {
  if(liveCount==LIVE_CAPACITY){
    liveHead=(liveHead+1)%LIVE_CAPACITY;
    --liveCount;
    ++liveDropped;
  }
  liveEvents[(liveHead+liveCount)%LIVE_CAPACITY]=ev;
  ++liveCount;
}
}  // namespace

bool hasLiveEvents(){return liveCount!=0 || liveHealth[0];}
size_t formatLiveBatch(char* buf,size_t capacity) {
  size_t used=strlen(liveHealth),count=0;
  memcpy(buf,liveHealth,used+1);
  while(count<liveCount && capacity-used>=1024) {
    formatEvent(buf+used,capacity-used,liveEvents[(liveHead+count)%LIVE_CAPACITY]);
    used+=strlen(buf+used);
    ++count;
  }
  return count;
}
void ackLiveBatch(size_t count) {
  liveHead=(liveHead+count)%LIVE_CAPACITY;
  liveCount-=count;
  liveAcked+=count;
  liveHealth[0]=0;
}

bool begin() {
  i2s_config_t cfg = {};
  cfg.mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_RX);
  cfg.sample_rate = 64000;   // 2.048 MHz BCLK startup at stereo / 16 bits
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
  cfg.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;
  cfg.communication_format = I2S_COMM_FORMAT_STAND_MSB;
  cfg.intr_alloc_flags = 0;
  cfg.dma_buf_count = 8;
  cfg.dma_buf_len = 512;
  cfg.use_apll = false;
  cfg.tx_desc_auto_clear = false;
  cfg.fixed_mclk = 0;
  esp_err_t e = i2s_driver_install(PORT, &cfg, 16, &eventQueue);
  if (e != ESP_OK) {
    Serial.printf("NZRT MIC install failed=%d\n", static_cast<int>(e));
    return false;
  }

  i2s_pin_config_t pins = {};
  pins.bck_io_num = CLK;
  pins.ws_io_num = DUMMY_WS;  // do not connect externally
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num = DATA;
  pins.mck_io_num = I2S_PIN_NO_CHANGE; // no clock output on BOOT GPIO0
  e = i2s_set_pin(PORT, &pins);
  if (e != ESP_OK) {
    Serial.printf("NZRT MIC pins failed=%d\n", static_cast<int>(e));
    i2s_driver_uninstall(PORT);
    return false;
  }

  delay(120);
  i2s_stop(PORT);
  e = i2s_set_clk(PORT, 96000, I2S_BITS_PER_SAMPLE_16BIT, I2S_CHANNEL_STEREO);
  if (e != ESP_OK) {
    Serial.printf("NZRT MIC clock failed=%d\n", static_cast<int>(e));
    i2s_driver_uninstall(PORT);
    return false;
  }
  e = i2s_start(PORT);
  if (e != ESP_OK) {
    Serial.printf("NZRT MIC start failed=%d\n", static_cast<int>(e));
    i2s_driver_uninstall(PORT);
    return false;
  }
  dspEnabledRequest=false;
  captureEnabledRequest=true;
  captureRunning=true;
  dayStandby=false;
  WildlifeDetector::reset();
  if(!allocatePool(EXT_BLOCKS,MALLOC_CAP_SPIRAM) && !allocatePool(INTERNAL_BLOCKS,MALLOC_CAP_INTERNAL)) {
    Serial.println("NZRT MIC failed allocating bounded DSP queue");
    i2s_driver_uninstall(PORT);
    return false;
  }
  Serial.printf("NZRT AUDIO_POOL blocks=%u block_bytes=%u memory=%s\n",poolCapacity,unsigned(BUFFER_BYTES),poolCapacity==EXT_BLOCKS?"psram":"internal");
  BaseType_t ok = xTaskCreatePinnedToCore(dspTask, "wildlife_dsp", 8192,
                                           nullptr, 2, &dspTaskHandle, 0);
  if(ok != pdPASS) {
    Serial.println("NZRT MIC failed creating low-priority DSP worker");
    releasePool();
    i2s_driver_uninstall(PORT);
    return false;
  }
  ok = xTaskCreatePinnedToCore(readerTask, "wildlife_mic", 6144,
                                           nullptr, 18, &captureTask, 1);
  if (ok != pdPASS) {
    Serial.println("NZRT MIC task allocation failed");
    vTaskDelete(dspTaskHandle);dspTaskHandle=nullptr;
    releasePool();
    i2s_driver_uninstall(PORT);
    return false;
  }
  started = true;
  sessionId = esp_random(); // Identifier only, not a wall-clock or cryptographic token.
  if(sessionId == 0) sessionId = 1;
  dspStartUptimeMs = millis();
  dspRunNumber = 1;
  Serial.println("NZRT MIC experimental legacy I2S: CLK GPIO1 DATA GPIO2 WS GPIO4 (unwired), target BCLK 3.072MHz");
  Serial.println("NZRT DSP bounded queue, worker core0 priority2, reader core1 priority18");
  Serial.printf("NZRT SESSION id=%08lX build=%s reset_reason=%d dsp=ON from_uptime_ms=%lu time=UNSYNCED\n",
                (unsigned long)sessionId, BUILD_ID, (int)esp_reset_reason(),
                (unsigned long)dspStartUptimeMs);
  // MeshCore mounted SPIFFS before begin(); a fresh marker separates records
  // from previous runs, even if power was cut unexpectedly.
  WildlifeJournal::Writer bootLog;
  if(bootLog) {
    bootLog.printf("NZRT SESSION id=%08lX build=%s reset_reason=%d dsp=ON from_uptime_ms=%lu time=UNSYNCED\n",
                   (unsigned long)sessionId, BUILD_ID, (int)esp_reset_reason(),
                   (unsigned long)dspStartUptimeMs);
    bootLog.printf("NZRT SCORE_POLICY session=%08lX version=%s shadow=1 base_trigger=1.8 window_ms=20 frame_samples=256 bat_like_min=65 harmonic_penalty_max=5 max_event_ms=10000 unverified=1\n",
      (unsigned long)sessionId,WildlifeScoring::VERSION);
    bootLog.close();
  } else {
    Serial.println("NZRT FIELD ERROR: cannot write boot marker to SPIFFS");
  }
  // Start autonomous detection on every boot; no serial client required.
  WildlifeML::begin(sessionId);
  dspEnabledRequest = true;
  return true;
}

void compareCounters(bool start,const char* phase){
 static Stats before;
 static uint32_t beforeEvents;
 Stats current;
 portENTER_CRITICAL(&statsLock);
 current=stats;
 if(start){stats.peakDepth=0;stats.peakDspUs=0;}
 portEXIT_CRITICAL(&statsLock);
 WildlifeDetector::Snapshot detector;WildlifeDetector::snapshot(detector);
 if(start){before=current;beforeEvents=detector.candidates;WildlifeJournal::startWriteTiming();return;}
 auto journal=WildlifeJournal::stopWriteTiming();
 Serial.printf("NZRT COMPARE TIMING stage=%s pool_blocks=%u queue_peak=%lu dsp_peak_us=%lu decode_us=%lu analysis_us=%lu pulse_score_us=%lu journal_us=%lu journal_max_op_us=%lu\n",
 phase,poolCapacity,(unsigned long)current.peakDepth,(unsigned long)current.peakDspUs,
 (unsigned long)(current.decodeUs-before.decodeUs),(unsigned long)(current.analysisUs-before.analysisUs),
 (unsigned long)(current.scoreUs-before.scoreUs),(unsigned long)journal.total,(unsigned long)journal.peak);
 Serial.printf("NZRT COMPARE COUNTERS stage=%s blocks=%lu done=%lu drops=%lu gaps=%lu dma_ovf=%lu read_errors=%lu short_reads=%lu over_budget=%lu candidates=%lu\n",
 phase,(unsigned long)(current.fullReads-before.fullReads),(unsigned long)(current.dspBlocksProcessed-before.dspBlocksProcessed),
 (unsigned long)(current.dspQueueDrops-before.dspQueueDrops),(unsigned long)(current.dspStreamResets-before.dspStreamResets),
 (unsigned long)(current.rxQueueOverflows-before.rxQueueOverflows),(unsigned long)(current.readErrors-before.readErrors),
 (unsigned long)(current.shortReads-before.shortReads),(unsigned long)(current.processOverBudget-before.processOverBudget),
 (unsigned long)(detector.candidates-beforeEvents));
}
void printHealthIfDue() {
  if (!started) {
    static uint32_t lastRetry=0;
    if(millis()-lastRetry<30000UL)return;
    lastRetry=millis();
    if(!begin()){
      snprintf(liveHealth,sizeof(liveHealth),
        "NZRT FIELD health=1 utc=%lu state=MIC_INIT_FAILED retry_s=30\n",
        (unsigned long)WildlifeTime::epochForUptime(lastRetry));
      Serial.print(liveHealth);
      WildlifeJournal::Writer log;
      if(log){log.print(liveHealth);log.close();}
    }
    return;
  }
  WildlifeML::tick();
  // Audio samples are processed only in the DMA task; flash writes occur here
  // on the main loop, batched every ten seconds to minimise interference.
  static WildlifeDetector::Event pending[64];
  static size_t pendingN=0;
  static uint32_t lastFlush=0;
  static uint32_t ramDropped=0;
  static uint32_t lastErrorReport=0;
  WildlifeDetector::Event ev;
  char line[1024];
  for(unsigned i=0; i<8 && WildlifeDetector::pop(ev);++i) {
    // Always drain fresh detector events, including during flash failure.
    // Oldest pending journal-only metadata is expendable after backup.
    if(pendingN==64) {
      for(size_t j=1;j<pendingN;++j)pending[j-1]=pending[j];
      --pendingN;++ramDropped;
    }
    formatEvent(line,sizeof(line),ev);
    Serial.print(line); // live USB telemetry independent of SPIFFS
    queueLive(ev);
    pending[pendingN++]=ev;
  }
  uint32_t checkNow=millis();
  if(pendingN && ((pendingN==64 && checkNow-lastFlush>=1000UL) || checkNow-lastFlush>=10000UL)) {
    WildlifeJournal::Writer f;
    if(f) {
      bool complete=true;
      for(size_t i=0;i<pendingN;++i) {
        formatEvent(line,sizeof(line),pending[i]);
        if(f.print(line)!=strlen(line)) {
          ++journalWriteFailures;
          if(!lastErrorReport || (uint32_t)(checkNow-lastErrorReport)>=60000UL) {
            lastErrorReport=checkNow;
            Serial.println("NZRT FIELD ERROR: candidate journal short write; retry deferred");
          }
          // Retry the full batch. No prefix is confirmed until close verifies it.
          f.print("\n");
          complete=false;
          break;
        }
      }
      if(f.close() && complete) {
        for(size_t i=0;i<pendingN;++i)
          Serial.printf("NZRT CANDIDATE_SAVED session=%08lX run=%lu seq=%lu\n",
            (unsigned long)sessionId,(unsigned long)pending[i].run,(unsigned long)pending[i].seq);
        pendingN=0;
      }
      else if(complete) ++journalWriteFailures; // A failed flush may have persisted a prefix; idempotent session/run/seq.
    } else {
      ++journalWriteFailures;
      if(!lastErrorReport || (uint32_t)(checkNow-lastErrorReport)>=60000UL) {
        lastErrorReport=checkNow;
        Serial.println("NZRT FIELD ERROR: journal unavailable; recent events retained in RAM");
      }
    }
    lastFlush=checkNow;
  }
  static uint32_t lastReport = 0;
  static uint64_t lastBytes = 0;
  static uint32_t lastAlive = 0;
  uint32_t now = millis();
  if(now-lastAlive >= 10000UL) {
    lastAlive=now;
    Serial.printf("NZRT ALIVE session=%08lX t=%lus dsp=%s capture=%s mode=%s reset_reason=%d\n",
      (unsigned long)sessionId, (unsigned long)(now/1000),
      dspEnabledRequest?"ON":"OFF", captureRunning?"ON":"OFF",
      dayStandby?"DAY_STANDBY":"MONITORING", (int)esp_reset_reason());
  }
  if (now - lastReport < REPORT_MS) return;
  Serial.printf("NZRT EVENT_BUFFER pending=%lu capacity=64 ram_dropped_oldest=%lu flash_write_failures=%lu\n",
      (unsigned long)pendingN,(unsigned long)ramDropped,(unsigned long)journalWriteFailures);
  uint32_t dt = now - lastReport;
  lastReport = now;

  portENTER_CRITICAL(&statsLock);
  Stats snap = stats;
  portEXIT_CRITICAL(&statsLock);

  uint32_t bps = static_cast<uint32_t>(((snap.bytes - lastBytes) * 1000ULL) / dt);
  lastBytes = snap.bytes;
  float density = snap.bytes
      ? (100.0 * static_cast<double>(snap.ones) / (8.0 * static_cast<double>(snap.bytes))) : 0.0;
  WildlifeDetector::Snapshot ds;
  WildlifeDetector::snapshot(ds);
  static uint32_t previousRun=0,previousWindows=0,previousDrops=0,previousGaps=0,lastHealth=0;
  static bool wasDegraded=false;
  if(captureEnabledRequest && dspEnabledRequest && dspRunNumber==previousRun) {
    bool stalled=WildlifeML::compareStage()!=1 && ds.windows==previousWindows;
    bool degraded=stalled || snap.dspQueueDrops!=previousDrops || snap.dspStreamResets!=previousGaps;
    if(degraded || wasDegraded || !lastHealth || now-lastHealth>=300000UL) {
      lastHealth=now;
      snprintf(liveHealth,sizeof(liveHealth),
        "NZRT FIELD health=1 session=%08lX run=%lu utc=%lu state=%s windows_delta=%lu dsp_drop_delta=%lu live_dropped=%lu\n",
        (unsigned long)sessionId,(unsigned long)dspRunNumber,(unsigned long)WildlifeTime::epochForUptime(now),
        stalled?"STALLED":(degraded?"GAPS":"MONITORING"),(unsigned long)(ds.windows-previousWindows),
        (unsigned long)(snap.dspQueueDrops-previousDrops),(unsigned long)liveDropped);
      Serial.print(liveHealth);
      WildlifeJournal::Writer healthLog;
      if(healthLog){healthLog.print(liveHealth);healthLog.close();}
    }
    wasDegraded=degraded;
  }
  previousRun=dspRunNumber;
  previousWindows=ds.windows;
  previousDrops=snap.dspQueueDrops;
  previousGaps=snap.dspStreamResets;
  Serial.printf("NZRT LIVE pending=%u acked=%lu dropped=%lu clip_holds=%lu\n",unsigned(liveCount),(unsigned long)liveAcked,(unsigned long)liveDropped,(unsigned long)WildlifeDetector::optionalClipHolds());
  Serial.printf("NZRT MIC session=%08lX t=%lus mode=%s capture=%s bps=%lu density=%.3f%% blocks=%lu short=%lu errors=%lu legacy_rx_q_ovf=%lu worstRead=%luus worstDSP=%luus dspOver=%lu dsp_drop=%lu dsp_gap=%lu dsp_done=%lu dsp_qmax=%lu\n",
                (unsigned long)sessionId,
                static_cast<unsigned long>(now/1000),
                dayStandby?"DAY_STANDBY":"MONITORING",
                captureRunning?"ON":"OFF",
                static_cast<unsigned long>(bps), density,
                static_cast<unsigned long>(snap.fullReads),
                static_cast<unsigned long>(snap.shortReads),
                static_cast<unsigned long>(snap.readErrors),
                static_cast<unsigned long>(snap.rxQueueOverflows),
                static_cast<unsigned long>(snap.maxReadUs),
                static_cast<unsigned long>(snap.maxProcessUs),
                static_cast<unsigned long>(snap.processOverBudget),
                static_cast<unsigned long>(snap.dspQueueDrops),
                static_cast<unsigned long>(snap.dspStreamResets),
                static_cast<unsigned long>(snap.dspBlocksProcessed),
                static_cast<unsigned long>(snap.maxQueueDepth));

  Serial.printf("NZRT BAND session=%08lX 18-45kHz windows=%lu candidates=%lu rms=%.7f noise=%.7f peak=%.2fx (NOT BAT ID)\n",
    (unsigned long)sessionId, static_cast<unsigned long>(ds.windows),static_cast<unsigned long>(ds.candidates),
    ds.band_rms,ds.noise_rms,ds.peak_ratio);
  Serial.printf("NZRT SCORE session=%08lX version=%s shadow=1 bat_like=%lu uncertain=%lu event_queue_lost=%lu input_gaps=%lu\n",
    (unsigned long)sessionId,WildlifeScoring::VERSION,(unsigned long)ds.bat_like,
    (unsigned long)ds.uncertain,(unsigned long)ds.event_queue_lost,(unsigned long)ds.input_gaps);
  // Field-test journal: use MeshCore's existing /packet_log so the stock
  // 'log' command also returns mic/uptime evidence after power cycles.
  // One heartbeat at ~60s, then every 5m; avoid a flash write every sample.
  // The upstream repeater mounts SPIFFS before WildlifeMic::begin().
  static uint32_t lastJournalMs = 0;
  if (lastJournalMs == 0 || now - lastJournalMs >= 300000UL) {
    lastJournalMs = now;
    WildlifeJournal::Writer journal;
    if (journal) {
      journal.printf(
          "NZRT FIELD session=%08lX uptime=%lus mode=%s capture=%s mic_bps=%lu density=%.3f%% blocks=%lu short=%lu read_err=%lu dma_q_ovf=%lu dsp_drop=%lu dsp_gap=%lu dspOver=%lu\n",
          (unsigned long)sessionId, static_cast<unsigned long>(now / 1000UL),
          dayStandby?"DAY_STANDBY":"MONITORING",
          captureRunning?"ON":"OFF",
          static_cast<unsigned long>(bps), density,
          static_cast<unsigned long>(snap.fullReads),
          static_cast<unsigned long>(snap.shortReads),
          static_cast<unsigned long>(snap.readErrors),
          static_cast<unsigned long>(snap.rxQueueOverflows),
          static_cast<unsigned long>(snap.dspQueueDrops),
          static_cast<unsigned long>(snap.dspStreamResets),
          static_cast<unsigned long>(snap.processOverBudget));
      journal.printf("NZRT BAND session=%08lX uptime=%lus utc=%lu time_source=%s windows=%lu candidates=%lu rms=%.7f noise=%.7f peak=%.2fx unverified=1\n",
         (unsigned long)sessionId, static_cast<unsigned long>(now/1000UL),
         (unsigned long)WildlifeTime::epochForUptime(now),WildlifeTime::source(),
         static_cast<unsigned long>(ds.windows),
         static_cast<unsigned long>(ds.candidates),ds.band_rms,ds.noise_rms,ds.peak_ratio);
      journal.printf("NZRT SCORE session=%08lX uptime=%lus utc=%lu time_source=%s version=%s shadow=1 bat_like=%lu uncertain=%lu event_queue_lost=%lu input_gaps=%lu\n",
        (unsigned long)sessionId,(unsigned long)(now/1000UL),
        (unsigned long)WildlifeTime::epochForUptime(now),WildlifeTime::source(),
        WildlifeScoring::VERSION,(unsigned long)ds.bat_like,(unsigned long)ds.uncertain,
        (unsigned long)ds.event_queue_lost,(unsigned long)ds.input_gaps);
      WildlifeML::status(journal);
      WildlifeJournal::status(journal);
      journal.close();
    } else {
      Serial.println("NZRT FIELD flash journal open failed");
    }
  }
}
void setDaytimeStandby(bool standby) {
  if (!started || dayStandby==standby) return;
  uint32_t at=millis();
  if(standby) {
    // DSP leaves all pending event records available to main-loop flushing.
    dspEnabledRequest=false;
    captureEnabledRequest=false; // reader will stop I2S after its current block
    dayStandby=true;
  } else {
    // Reset the analysis time origin for the new nighttime segment.
    // Each transition must have a fresh run number.
    dspStartUptimeMs=at;
    ++dspRunNumber;
    captureEnabledRequest=true;
    dspEnabledRequest=true;
    dayStandby=false;
  }
  Serial.printf("NZRT DAY_MODE session=%08lX run=%lu state=%s uptime_ms=%lu utc=%lu time_source=%s capture_request=%s meshcore=ON\n",
     (unsigned long)sessionId,(unsigned long)dspRunNumber,
     standby?"STANDBY":"MONITORING",(unsigned long)at,
     (unsigned long)WildlifeTime::epochForUptime(at),
     WildlifeTime::source(),captureEnabledRequest?"ON":"OFF");
  WildlifeJournal::Writer marker;
  if(marker) {
    marker.printf("NZRT DAY_MODE session=%08lX run=%lu state=%s uptime_ms=%lu utc=%lu time_source=%s capture_request=%s meshcore=ON\n",
      (unsigned long)sessionId,(unsigned long)dspRunNumber,
      standby?"STANDBY":"MONITORING",(unsigned long)at,
      (unsigned long)WildlifeTime::epochForUptime(at),
      WildlifeTime::source(),captureEnabledRequest?"ON":"OFF");
    marker.close();
  }
}
bool daytimeStandby() {return dayStandby;}
void setDspEnabled(bool enable) {
  bool wasEnabled=dspEnabledRequest;
  if(enable != wasEnabled) {
    if(enable) {dspStartUptimeMs=millis();++dspRunNumber;}
    dspEnabledRequest=enable;
    WildlifeJournal::Writer marker;
    if(marker) {
      marker.printf("NZRT DSP_SWITCH session=%08lX run=%lu uptime_ms=%lu dsp=%s\n",
        (unsigned long)sessionId, (unsigned long)dspRunNumber,
        (unsigned long)millis(), enable?"ON":"OFF");
      marker.close();
    }
  }
  Serial.printf("NZRT DSP requested=%s build=%s\n",enable?"ON":"OFF",BUILD_ID);
}
void printStatus() {
  WildlifeML::status();
  WildlifeJournal::status();
  WildlifeDetector::Snapshot ds;
  WildlifeDetector::snapshot(ds);
  Serial.printf("NZRT DIAG build=%s session=%08lX run=%lu dsp=%s capture=%s day_mode=%s uptime=%lus dsp_start_uptime_ms=%lu reset_reason=%d utc=%lu time_source=%s\n",
    BUILD_ID, (unsigned long)sessionId, (unsigned long)dspRunNumber,
    dspEnabledRequest?"ON":"OFF", captureRunning?"ON":"OFF",
    dayStandby?"STANDBY":"MONITORING", (unsigned long)(millis()/1000),
    (unsigned long)dspStartUptimeMs, (int)esp_reset_reason(),
    (unsigned long)WildlifeTime::epochForUptime(millis()),WildlifeTime::source());
  size_t storageTotal=SPIFFS.totalBytes(),storageUsed=SPIFFS.usedBytes();
  Serial.printf("NZRT STORAGE total_bytes=%lu used_bytes=%lu free_bytes=%lu candidate_write_failures=%lu\n",
    (unsigned long)storageTotal,(unsigned long)storageUsed,
    (unsigned long)(storageTotal>storageUsed?storageTotal-storageUsed:0),
    (unsigned long)journalWriteFailures);
  Serial.printf("NZRT SCORE status session=%08lX version=%s shadow=1 bat_like=%lu uncertain=%lu event_queue_lost=%lu input_gaps=%lu\n",
    (unsigned long)sessionId,WildlifeScoring::VERSION,(unsigned long)ds.bat_like,
    (unsigned long)ds.uncertain,(unsigned long)ds.event_queue_lost,(unsigned long)ds.input_gaps);
  Serial.printf("NZRT BAND status session=%08lX 18-45kHz windows=%lu candidates=%lu rms=%.7f background=%.7f max_ratio=%.2fx unverified=1\n",
    (unsigned long)sessionId,
    static_cast<unsigned long>(ds.windows),static_cast<unsigned long>(ds.candidates),
    ds.band_rms,ds.noise_rms,ds.peak_ratio);
}
} // namespace WildlifeMic

