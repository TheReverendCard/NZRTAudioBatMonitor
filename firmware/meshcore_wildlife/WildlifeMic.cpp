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
#include "WildlifeDetector.h"
#include "WildlifeTime.h"
#include <SPIFFS.h>  // same flash filesystem used by upstream MeshCore repeater
#include <driver/i2s.h>
#include <esp_timer.h>
#include <esp_system.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>

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
constexpr const char* BUILD_ID = "NZRT-FIELD-PILOT-4";
uint32_t sessionId = 0;
uint32_t dspStartUptimeMs = 0;
uint32_t dspRunNumber = 0;

constexpr UBaseType_t DSP_QUEUE_BLOCKS = 8;
struct RawBlock {
  uint32_t seq;
  uint32_t n;
  uint32_t words[BUFFER_BYTES / sizeof(uint32_t)];
};


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

};
Stats stats;
bool started = false;

// The capture reader is high-priority and must never perform FIR/PCM work.
// A bounded queue decouples radio/USB servicing from slower audio analysis.
void readerTask(void*) {
  RawBlock pkt = {};
  uint32_t seq = 0;
  for (;;) {
    // Only the reader task owns I2S start/stop, so the scheduler cannot race
    // an in-progress i2s_read() from another core. LoRa keeps running.
    if(!captureEnabledRequest) {
      if(captureRunning) {
        esp_err_t rc=i2s_stop(PORT);
        if(rc!=ESP_OK) Serial.printf("NZRT DAY I2S_STOP_FAILED error=%d\n",(int)rc);
        else captureRunning=false;
      }
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
    uint32_t ones = 0;
    if(status == ESP_OK) {
      for(size_t i=0; i<n/sizeof(uint32_t); ++i)
        ones += static_cast<uint32_t>(__builtin_popcount(pkt.words[i]));
      pkt.seq = ++seq;
      pkt.n = static_cast<uint32_t>(n);
    }
    uint32_t queueDrop=0, queueDepth=0;
    if(status == ESP_OK && n && dspEnabledRequest) {
      // Non-blocking. Prefer dropping an analysis block to missing I2S DMA.
      if(!dspQueue || xQueueSend(dspQueue, &pkt, 0) != pdPASS)
        ++queueDrop;
      else
        queueDepth = static_cast<uint32_t>(uxQueueMessagesWaiting(dspQueue));
    }
    uint32_t overflowDelta=0;
    i2s_event_t event;
    while(eventQueue && xQueueReceive(eventQueue, &event, 0) == pdTRUE)
      if(event.type == I2S_EVENT_RX_Q_OVF) ++overflowDelta;
    portENTER_CRITICAL(&statsLock);
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
    if(status != ESP_OK) vTaskDelay(pdMS_TO_TICKS(2));
  }
}
void dspTask(void*) {
  RawBlock pkt;
  uint32_t prevSeq=0, processed=0;
  bool running=false;
  for(;;) {
    bool requested=dspEnabledRequest;
    if(requested!=running) {
      running=requested;
      WildlifeDetector::reset();
      prevSeq=0;
      // Only the DSP task resets its FIFO/algorithm state.
      xQueueReset(dspQueue);
    }
    if(!running) {vTaskDelay(pdMS_TO_TICKS(25));continue;}
    if(xQueueReceive(dspQueue,&pkt,pdMS_TO_TICKS(100)) != pdTRUE) {
      vTaskDelay(1);
      continue;
    }
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
    WildlifeDetector::consume(reinterpret_cast<const uint8_t*>(pkt.words),pkt.n);
    uint32_t elapsed=static_cast<uint32_t>(esp_timer_get_time()-before);
    portENTER_CRITICAL(&statsLock);
    if(elapsed>stats.maxProcessUs)stats.maxProcessUs=elapsed;
    if(pkt.n && elapsed>(pkt.n*1000000UL/384000UL))++stats.processOverBudget;
    ++stats.dspBlocksProcessed;
    portEXIT_CRITICAL(&statsLock);
    // Give IDLE0 / low-priority Wi-Fi housekeeping guaranteed CPU time.
    // Yield to core0 idle/Wi-Fi without consuming ~5% of DSP time.
    if((++processed & 15U)==0) vTaskDelay(1);
  }
}
}  // namespace

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
  dspQueue = xQueueCreate(DSP_QUEUE_BLOCKS, sizeof(RawBlock));
  if(!dspQueue) {
    Serial.println("NZRT MIC failed allocating bounded DSP queue");
    i2s_driver_uninstall(PORT);
    return false;
  }
  BaseType_t ok = xTaskCreatePinnedToCore(dspTask, "wildlife_dsp", 8192,
                                           nullptr, 1, &dspTaskHandle, 0);
  if(ok != pdPASS) {
    Serial.println("NZRT MIC failed creating low-priority DSP worker");
    vQueueDelete(dspQueue);dspQueue=nullptr;
    i2s_driver_uninstall(PORT);
    return false;
  }
  ok = xTaskCreatePinnedToCore(readerTask, "wildlife_mic", 6144,
                                           nullptr, 18, &captureTask, 1);
  if (ok != pdPASS) {
    Serial.println("NZRT MIC task allocation failed");
    vTaskDelete(dspTaskHandle);dspTaskHandle=nullptr;
    vQueueDelete(dspQueue);dspQueue=nullptr;
    i2s_driver_uninstall(PORT);
    return false;
  }
  started = true;
  sessionId = esp_random(); // Identifier only, not a wall-clock or cryptographic token.
  if(sessionId == 0) sessionId = 1;
  dspStartUptimeMs = millis();
  dspRunNumber = 1;
  Serial.println("NZRT MIC experimental legacy I2S: CLK GPIO1 DATA GPIO2 WS GPIO4 (unwired), target BCLK 3.072MHz");
  Serial.println("NZRT DSP bounded queue, worker core0 priority1, reader core1 priority18");
  Serial.printf("NZRT SESSION id=%08lX build=%s reset_reason=%d dsp=ON from_uptime_ms=%lu time=UNSYNCED\n",
                (unsigned long)sessionId, BUILD_ID, (int)esp_reset_reason(),
                (unsigned long)dspStartUptimeMs);
  // MeshCore mounted SPIFFS before begin(); a fresh marker separates records
  // from previous runs, even if power was cut unexpectedly.
  File bootLog = SPIFFS.open("/packet_log", FILE_APPEND);
  if(bootLog) {
    bootLog.printf("NZRT SESSION id=%08lX build=%s reset_reason=%d dsp=ON from_uptime_ms=%lu time=UNSYNCED\n",
                   (unsigned long)sessionId, BUILD_ID, (int)esp_reset_reason(),
                   (unsigned long)dspStartUptimeMs);
    bootLog.close();
  } else {
    Serial.println("NZRT FIELD ERROR: cannot write boot marker to SPIFFS");
  }
  // Start autonomous detection on every boot; no serial client required.
  dspEnabledRequest = true;
  return true;
}

void printHealthIfDue() {
  if (!started) return;
  // Audio samples are processed only in the DMA task; flash writes occur here
  // on the main loop, batched every ten seconds to minimise interference.
  static WildlifeDetector::Event pending[64];
  static size_t pendingN=0;
  static uint32_t lastFlush=0;
  WildlifeDetector::Event ev;
  for(unsigned i=0; i<8 && WildlifeDetector::pop(ev);++i) {
    uint32_t startUtc=WildlifeTime::epochForUptime(dspStartUptimeMs+ev.start_ms);
    uint32_t endUtc=WildlifeTime::epochForUptime(dspStartUptimeMs+ev.end_ms);
    Serial.printf("NZRT CANDIDATE session=%08lX run=%lu seq=%lu from_ms=%lu to_ms=%lu utc_start=%lu utc_end=%lu time_source=%s peak=%.2fx (UNVERIFIED)\n",
       (unsigned long)sessionId, (unsigned long)dspRunNumber,
       static_cast<unsigned long>(ev.seq),static_cast<unsigned long>(ev.start_ms),
       static_cast<unsigned long>(ev.end_ms),(unsigned long)startUtc,
       (unsigned long)endUtc,WildlifeTime::source(),ev.peak_ratio);
    if(pendingN<64)pending[pendingN++]=ev;
  }
  uint32_t checkNow=millis();
  if(pendingN && (pendingN==64 || checkNow-lastFlush>=10000UL)) {
    File f=SPIFFS.open("/packet_log",FILE_APPEND);
    if(f) {
      for(size_t i=0;i<pendingN;++i) {
        uint32_t sUtc=WildlifeTime::epochForUptime(dspStartUptimeMs+pending[i].start_ms);
        uint32_t eUtc=WildlifeTime::epochForUptime(dspStartUptimeMs+pending[i].end_ms);
        f.printf("NZRT CANDIDATE session=%08lX run=%lu seq=%lu from_ms=%lu to_ms=%lu utc_start=%lu utc_end=%lu time_source=%s peak=%.2fx unverified=1\n",
          (unsigned long)sessionId, (unsigned long)dspRunNumber,
          static_cast<unsigned long>(pending[i].seq),static_cast<unsigned long>(pending[i].start_ms),
          static_cast<unsigned long>(pending[i].end_ms),(unsigned long)sUtc,
          (unsigned long)eUtc,WildlifeTime::source(),pending[i].peak_ratio);
      }
      f.close();pendingN=0;
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
  Serial.printf("NZRT MIC session=%08lX t=%lus mode=%s capture=%s bps=%lu density=%.3f%% blocks=%lu short=%lu errors=%lu legacy_rx_q_ovf=%lu worstRead=%luus worstDSP=%luus dspOver=%lu dsp_drop=%lu dsp_gap=%lu dsp_done=%lu dsp_qmax=%lu\n",
                (unsigned long)sessionId,
                dayStandby?"DAY_STANDBY":"MONITORING",
                captureRunning?"ON":"OFF",
                static_cast<unsigned long>(now/1000),
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
  // Field-test journal: use MeshCore's existing /packet_log so the stock
  // 'log' command also returns mic/uptime evidence after power cycles.
  // One heartbeat at ~60s, then every 5m; avoid a flash write every sample.
  // The upstream repeater mounts SPIFFS before WildlifeMic::begin().
  static uint32_t lastJournalMs = 0;
  if (lastJournalMs == 0 || now - lastJournalMs >= 300000UL) {
    lastJournalMs = now;
    File journal = SPIFFS.open("/packet_log", FILE_APPEND);
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
  File marker=SPIFFS.open("/packet_log",FILE_APPEND);
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
    dspEnabledRequest=enable;
    if(enable) {dspStartUptimeMs=millis();++dspRunNumber;}
    File marker=SPIFFS.open("/packet_log",FILE_APPEND);
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
  WildlifeDetector::Snapshot ds;
  WildlifeDetector::snapshot(ds);
  Serial.printf("NZRT DIAG build=%s session=%08lX run=%lu dsp=%s capture=%s day_mode=%s uptime=%lus dsp_start_uptime_ms=%lu reset_reason=%d utc=%lu time_source=%s\n",
    BUILD_ID, (unsigned long)sessionId, (unsigned long)dspRunNumber,
    dspEnabledRequest?"ON":"OFF", captureRunning?"ON":"OFF",
    dayStandby?"STANDBY":"MONITORING", (unsigned long)(millis()/1000),
    (unsigned long)dspStartUptimeMs, (int)esp_reset_reason(),
    (unsigned long)WildlifeTime::epochForUptime(millis()),WildlifeTime::source());
  Serial.printf("NZRT BAND status session=%08lX 18-45kHz windows=%lu candidates=%lu rms=%.7f background=%.7f max_ratio=%.2fx unverified=1\n",
    (unsigned long)sessionId,
    static_cast<unsigned long>(ds.windows),static_cast<unsigned long>(ds.candidates),
    ds.band_rms,ds.noise_rms,ds.peak_ratio);
}
} // namespace WildlifeMic
