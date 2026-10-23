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
#include <driver/i2s.h>
#include <esp_timer.h>
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

struct Stats {
  uint64_t bytes = 0;
  uint64_t ones = 0;
  uint32_t fullReads = 0;
  uint32_t shortReads = 0;
  uint32_t readErrors = 0;
  uint32_t rxQueueOverflows = 0;
  uint32_t maxReadUs = 0;
};
Stats stats;
bool started = false;

void readerTask(void*) {
  uint32_t raw[BUFFER_BYTES / sizeof(uint32_t)];
  for (;;) {
    size_t n = 0;
    int64_t before = esp_timer_get_time();
    esp_err_t status = i2s_read(PORT, raw, sizeof(raw), &n, pdMS_TO_TICKS(1000));
    uint32_t elapsed = static_cast<uint32_t>(esp_timer_get_time() - before);

    uint32_t ones = 0;
    if (status == ESP_OK) {
      for (size_t i = 0; i < n / sizeof(uint32_t); ++i) {
        ones += static_cast<uint32_t>(__builtin_popcount(raw[i]));
      }
    }
    uint32_t overflowDelta = 0;
    i2s_event_t event;
    while (eventQueue && xQueueReceive(eventQueue, &event, 0) == pdTRUE) {
      if (event.type == I2S_EVENT_RX_Q_OVF) ++overflowDelta;
    }

    portENTER_CRITICAL(&statsLock);
    stats.bytes += n;
    stats.ones += ones;
    stats.rxQueueOverflows += overflowDelta;
    if (status != ESP_OK) ++stats.readErrors;
    else if (n != sizeof(raw)) ++stats.shortReads;
    else ++stats.fullReads;
    if (elapsed > stats.maxReadUs) stats.maxReadUs = elapsed;
    portEXIT_CRITICAL(&statsLock);

    if (status != ESP_OK) vTaskDelay(pdMS_TO_TICKS(2));
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
  BaseType_t ok = xTaskCreatePinnedToCore(readerTask, "wildlife_mic", 6144,
                                           nullptr, 18, &captureTask, 1);
  if (ok != pdPASS) {
    Serial.println("NZRT MIC task allocation failed");
    i2s_driver_uninstall(PORT);
    return false;
  }
  started = true;
  Serial.println("NZRT MIC experimental legacy I2S: CLK GPIO1 DATA GPIO2 WS GPIO4 (unwired), target BCLK 3.072MHz");
  return true;
}

void printHealthIfDue() {
  if (!started) return;
  static uint32_t lastReport = 0;
  static uint64_t lastBytes = 0;
  uint32_t now = millis();
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
  Serial.printf("NZRT MIC t=%lus bps=%lu density=%.3f%% blocks=%lu short=%lu errors=%lu legacy_rx_q_ovf=%lu worstRead=%luus\n",
                static_cast<unsigned long>(now/1000),
                static_cast<unsigned long>(bps), density,
                static_cast<unsigned long>(snap.fullReads),
                static_cast<unsigned long>(snap.shortReads),
                static_cast<unsigned long>(snap.readErrors),
                static_cast<unsigned long>(snap.rxQueueOverflows),
                static_cast<unsigned long>(snap.maxReadUs));
}
} // namespace WildlifeMic
