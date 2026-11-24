/*
  NZRT Wildlife Node - v0.1 hardware bring-up
  Experimental branch only: raw LoRa + mic, no SD / no classifiers / no Wi-Fi yet.
  v0.2 matches Open Transit Display v0.8.4a RF settings for passive RX
  and an explicitly requested small NZRT1|PING packet. Never triggers OTD actions.
  This is NOT MeshCore! Do not flash as a working mesh sensor/repeater.
  Mic: CLK=D0/GPIO1, DATA=D1/GPIO2, SEL strapped to GND by the breakout.
  Wio-SX1262: B2B connector, SPI GPIO7/8/9, NSS41, IRQ39, RST42, BUSY40, RF_SW38.

  Requires Arduino-ESP32 3.3.12 and RadioLib (tested by CI where available).
  IMPORTANT: Attach the correct LoRa antenna BEFORE enabling TX.
  This is point-to-point raw LoRa, NOT Meshtastic or LoRaWAN.
*/
#include <Arduino.h>
#include <SPI.h>
#include <RadioLib.h>
#include "WildlifeTypes.h"
#include "driver/i2s_std.h"
#include "driver/i2s_common.h"
#include "esp_err.h"
#include "esp_timer.h"

static constexpr gpio_num_t MIC_CLK_PIN = GPIO_NUM_1;  // XIAO D0
static constexpr gpio_num_t MIC_DATA_PIN = GPIO_NUM_2; // XIAO D1
static constexpr gpio_num_t DUMMY_WS_PIN = GPIO_NUM_5; // XIAO D4; NO external connection

static constexpr int LORA_SCK = 7;
static constexpr int LORA_MISO = 8;
static constexpr int LORA_MOSI = 9;
static constexpr int LORA_NSS = 41;
static constexpr int LORA_DIO1 = 39;
static constexpr int LORA_RESET = 42;
static constexpr int LORA_BUSY = 40;
static constexpr int LORA_RF_SW = 38;

// Initial test settings only. Set these to match a separate receiving radio.
static constexpr float LORA_FREQUENCY_MHZ = 915.0f;
static constexpr float LORA_BANDWIDTH_KHZ = 125.0f;
static constexpr uint8_t LORA_SPREADING_FACTOR = 9;
static constexpr uint8_t LORA_CODING_RATE = 7;   // 4/7: OTD 0.8.4a
static constexpr int8_t LORA_TX_POWER_DBM = 10;
static constexpr float LORA_TCXO_VOLTAGE = 1.8f;
static constexpr uint32_t STATUS_PERIOD_MS = 5000;
static constexpr uint32_t LORA_PERIOD_MS = 30000;

static SX1262 radio = new Module(LORA_NSS, LORA_DIO1, LORA_RESET, LORA_BUSY);
static i2s_chan_handle_t rxChannel = nullptr;
static TaskHandle_t audioTaskHandle = nullptr;
static portMUX_TYPE statsLock = portMUX_INITIALIZER_UNLOCKED;
static volatile uint32_t dmaOverflows = 0;
static bool radioReady = false;
// Opt-in raw bench TX. This is NOT MeshCore protocol and will not mesh.
static bool txEnabled = false;
static uint32_t txSequence = 0;
static uint32_t txOk = 0;
static uint32_t txFailed = 0;
static uint32_t rxOk = 0, rxBad = 0, pingSeq = 0;
static volatile bool receivedRadioIrq = false;
static void IRAM_ATTR onRadioReceive() { receivedRadioIrq = true; }

static CaptureStats counters;

static bool IRAM_ATTR onDmaOverflow(i2s_chan_handle_t, i2s_event_data_t*, void*) {
  ++dmaOverflows;
  return false;
}

static bool initSampler(uint32_t frameRate) {
  i2s_chan_config_t channelConfig =
      I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
  channelConfig.dma_desc_num = 8;
  channelConfig.dma_frame_num = 512;

  esp_err_t e = i2s_new_channel(&channelConfig, nullptr, &rxChannel);
  if (e != ESP_OK) {
    Serial.printf("MIC new channel FAILED: %d\n", (int)e);
    return false;
  }

  i2s_event_callbacks_t callbacks = {};
  callbacks.on_recv_q_ovf = onDmaOverflow;
  e = i2s_channel_register_event_callback(rxChannel, &callbacks, nullptr);
  if (e != ESP_OK) {
    Serial.printf("MIC callbacks FAILED: %d\n", (int)e);
    return false;
  }

  i2s_std_config_t cfg = {
    .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(frameRate),
    .slot_cfg = I2S_STD_MSB_SLOT_DEFAULT_CONFIG(
        I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO),
    .gpio_cfg = {
      .mclk = I2S_GPIO_UNUSED,
      .bclk = MIC_CLK_PIN,
      .ws = DUMMY_WS_PIN,
      .dout = I2S_GPIO_UNUSED,
      .din = MIC_DATA_PIN,
      .invert_flags = {
        .mclk_inv = false,
        .bclk_inv = false,
        .ws_inv = false,
      },
    },
  };
  e = i2s_channel_init_std_mode(rxChannel, &cfg);
  if (e != ESP_OK) {
    Serial.printf("MIC init STD FAILED: %d\n", (int)e);
    return false;
  }
  e = i2s_channel_enable(rxChannel);
  if (e != ESP_OK) {
    Serial.printf("MIC enable STD FAILED: %d\n", (int)e);
    return false;
  }
  return true;
}

static bool startMicrophone() {
  // Use the validated recorder's standard-clock startup followed by the
  // ultrasonic 3.072 MHz clock. Only the GPIO routing differs.
  // 64 kHz * 2 slots * 16 bits = 2.048 MHz initial BCLK.
  if (!initSampler(64000)) return false;
  delay(120);

  esp_err_t e = i2s_channel_disable(rxChannel);
  if (e != ESP_OK) {
    Serial.printf("MIC disable FAILED: %d\n", (int)e);
    return false;
  }
  i2s_std_clk_config_t clockConfig = I2S_STD_CLK_DEFAULT_CONFIG(96000);
  e = i2s_channel_reconfig_std_clock(rxChannel, &clockConfig);
  if (e != ESP_OK) {
    Serial.printf("MIC 3.072MHz reconfig FAILED: %d\n", (int)e);
    return false;
  }
  e = i2s_channel_enable(rxChannel);
  if (e != ESP_OK) {
    Serial.printf("MIC ultrasonic start FAILED: %d\n", (int)e);
    return false;
  }
  delay(30);
  Serial.println("MIC started: raw I2S/MSB, 96k x stereo 16-bit, BCLK=3.072MHz");
  return true;
}

static void micTask(void*) {
  // 2,048 bytes / 384,000 bytes/s = approximately 5.33 ms per read.
  static uint32_t words[512];
  for (;;) {
    size_t n = 0;
    uint64_t beforeUs = (uint64_t)esp_timer_get_time();
    esp_err_t e = i2s_channel_read(
        rxChannel, words, sizeof(words), &n, pdMS_TO_TICKS(1000));
    uint32_t elapsed = (uint32_t)((uint64_t)esp_timer_get_time() - beforeUs);

    uint32_t ones = 0;
    if (e == ESP_OK && n > 0) {
      for (size_t i = 0; i < n / sizeof(uint32_t); ++i) {
        ones += (uint32_t)__builtin_popcount(words[i]);
      }
    }
    portENTER_CRITICAL(&statsLock);
    counters.bytes += n;
    counters.oneBits += ones;
    if (e != ESP_OK) {
      ++counters.readErrors;
      counters.lastReadError = (int)e;
    } else if (n != sizeof(words)) {
      ++counters.shortReads;
    } else {
      ++counters.goodBlocks;
    }
    if (elapsed > counters.worstReadUs) counters.worstReadUs = elapsed;
    portEXIT_CRITICAL(&statsLock);

    if (e != ESP_OK) vTaskDelay(pdMS_TO_TICKS(2));
  }
}

static CaptureStats snapshot() {
  portENTER_CRITICAL(&statsLock);
  CaptureStats s = counters;
  portEXIT_CRITICAL(&statsLock);
  return s;
}

static void printHealth(const CaptureStats& s, uint64_t bytesSince, uint32_t intervalMs) {
  double onesPct = s.bytes ? (100.0 * (double)s.oneBits / (8.0 * (double)s.bytes)) : 0.0;
  uint32_t bps = intervalMs ? (uint32_t)((bytesSince * 1000ULL) / intervalMs) : 0;
  Serial.printf("HEALTH t=%lus bps=%lu PDM_ones=%.3f%% blocks=%lu short=%lu readerr=%lu DMAovf=%lu worstRead=%luus lastErr=%d LoRa=%s txOK=%lu txFail=%lu\n",
                (unsigned long)(millis() / 1000UL),
                (unsigned long)bps,
                onesPct,
                (unsigned long)s.goodBlocks,
                (unsigned long)s.shortReads,
                (unsigned long)s.readErrors,
                (unsigned long)dmaOverflows,
                (unsigned long)s.worstReadUs,
                s.lastReadError,
                radioReady ? "READY" : "FAILED",
                (unsigned long)txOk, (unsigned long)txFailed);
}

static void initRadio() {
  // The radio uses the XIAO's B2B connector, NOT D0/D1.
  pinMode(LORA_RF_SW, OUTPUT);
  digitalWrite(LORA_RF_SW, HIGH);  // RX / idle external antenna switch
  pinMode(LORA_NSS, OUTPUT);
  digitalWrite(LORA_NSS, HIGH);
  SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_NSS);

  int16_t rc = radio.begin(
      LORA_FREQUENCY_MHZ,
      LORA_BANDWIDTH_KHZ,
      LORA_SPREADING_FACTOR,
      LORA_CODING_RATE,
      RADIOLIB_SX126X_SYNC_WORD_PRIVATE,
      LORA_TX_POWER_DBM,
      8,
      LORA_TCXO_VOLTAGE,
      false);
  if (rc != RADIOLIB_ERR_NONE) {
    Serial.printf("LoRa init FAILED: %d; mic test continues\n", (int)rc);
    return;
  }
  radio.setDio2AsRfSwitch(true);
  radio.setPacketReceivedAction(onRadioReceive);
  digitalWrite(LORA_RF_SW, HIGH);
  int16_t rx = radio.startReceive();
  if (rx != RADIOLIB_ERR_NONE) {
    Serial.printf("LoRa RX start error=%d; mic continues\n", (int)rx);
    return;
  }
  radioReady = true;
  Serial.printf("LoRa READY: %.1fMHz BW125 SF9 CR4/7 sync=0x12 10dBm TCXO1.8V\n",
                (double)LORA_FREQUENCY_MHZ);
}


static void serviceRadioRx() {
  if (!radioReady || !receivedRadioIrq) return;
  noInterrupts();
  receivedRadioIrq = false;
  interrupts();
  String packet;
  int16_t result = radio.readData(packet);
  if (result == RADIOLIB_ERR_NONE) {
    ++rxOk;
    String type = "OTHER";
    if (packet.startsWith("OTD2|")) type = "OTD2";
    else if (packet.startsWith("OTD1|")) type = "OTD1";
    else if (packet.startsWith("OTDL1|")) type = "OTDL1";
    else if (packet.startsWith("OTD3|")) type = "OTD3";
    else if (packet.startsWith("NZRT1|")) type = "NZRT1";
    Serial.printf("LORA RX_OK kind=%s len=%u RSSI=%.1f SNR=%.1f rx=%lu\n",
                  type.c_str(), (unsigned)packet.length(),
                  radio.getRSSI(), radio.getSNR(), (unsigned long)rxOk);
    // No OTD ACK, schedule update, or protocol interaction.
  } else {
    ++rxBad;
    Serial.printf("LORA RX_ERROR=%d count=%lu\n",(int)result,(unsigned long)rxBad);
  }
  digitalWrite(LORA_RF_SW, HIGH);
  result = radio.startReceive();
  if (result != RADIOLIB_ERR_NONE) {
    Serial.printf("LORA RX_RESTART_ERROR=%d\n", (int)result);
    radioReady = false;
  }
}

static void transmitRaw(const char *payload) {
  if (!radioReady) {
    Serial.println("LORA not ready: no TX");
    return;
  }
  radio.clearPacketReceivedAction();
  receivedRadioIrq = false;
  int16_t status = radio.standby();
  if (status != RADIOLIB_ERR_NONE)
    Serial.printf("LORA standby returned %d\n", (int)status);
  digitalWrite(LORA_RF_SW, LOW);
  delayMicroseconds(100);
  status = radio.transmit(payload);
  digitalWrite(LORA_RF_SW, HIGH);
  if (status == RADIOLIB_ERR_NONE) {
    ++txOk;
    Serial.printf("LORA TX_OK: %s\n", payload);
  } else {
    ++txFailed;
    Serial.printf("LORA TX_ERROR=%d: %s\n", (int)status, payload);
  }
  radio.setPacketReceivedAction(onRadioReceive);
  status = radio.startReceive();
  if (status != RADIOLIB_ERR_NONE) {
    Serial.printf("LORA RX_RESTART_ERROR=%d\n", (int)status);
    radioReady = false;
  }
}

static void sendPing() {
  char payload[72];
  snprintf(payload,sizeof(payload),"NZRT1|PING|WILDLIFE|%lu|%lu",
           (unsigned long)++pingSeq, (unsigned long)(millis()/1000UL));
  transmitRaw(payload);
}

static void sendHealth(const CaptureStats& s) {
  if (!radioReady || !txEnabled) return;
  char payload[112];
  // Raw LoRa P2P; NOT Meshtastic/LoRaWAN, NOT a bat/bird detection message.
  unsigned long pct_x100 = s.bytes ?
      (unsigned long)((s.oneBits * 10000ULL) / (s.bytes * 8ULL)) : 0;
  snprintf(payload, sizeof(payload), "NZRT1|H|%lu|%lu|%lu|%lu|%lu|%lu",
           (unsigned long)txSequence++,
           (unsigned long)(millis() / 1000UL),
           (unsigned long)(s.bytes / 1024ULL),
           pct_x100,
           (unsigned long)dmaOverflows,
           (unsigned long)s.readErrors);
  transmitRaw(payload);
}

void setup() {
  Serial.begin(115200);
  delay(1400);
  Serial.println();
  Serial.println("NZRT wildlife v0.2 - OTD v0.8.4a RX + MIC D0/D1; no SD");
  Serial.println("BENCH-ONLY raw LoRa, NOT MeshCore interoperable. TX disabled by default.");
  Serial.println("Antenna attached: p=one gateway PING; t=toggle periodic raw TX; s=status.");
  Serial.println("RX is passive. Do not open the transit gateway COM port.");
  Serial.println("Expected raw throughput ~384000 bytes/s and PDM one-density ~50%.");

  bool micReady = startMicrophone();
  if (micReady) {
    BaseType_t ok = xTaskCreatePinnedToCore(
        micTask, "mic_dma_reader", 6144, nullptr, 19,
        &audioTaskHandle, 1);
    if (ok != pdPASS) {
      Serial.println("MIC TASK FAILED: cannot read DMA; no reliable capture");
      micReady = false;
    }
  }
  if (!micReady) {
    Serial.println("MIC FAILURE: check D0/D1, 3V3/GND, SEL strap, board and USB power");
  }

  initRadio();  // Even if microphone failed, allow independent LoRa diagnosis.
}

void loop() {
  static uint32_t lastStatusMs = 0;
  static uint32_t lastTxMs = 0;
  static uint64_t previousBytes = 0;

  while (Serial.available()) {
    char key = (char)Serial.read();
    if (key == 't' || key == 'T') {
      txEnabled = !txEnabled;
      Serial.printf("LoRa TX %s\n", txEnabled ? "ENABLED" : "DISABLED");
    } else if (key == 'p' || key == 'P') {
      sendPing();
    } else if (key == 's' || key == 'S') {
      CaptureStats s = snapshot();
      printHealth(s, 0, 0);
    }
  }

  serviceRadioRx();
  uint32_t now = millis();
  if ((uint32_t)(now - lastStatusMs) >= STATUS_PERIOD_MS) {
    uint32_t elapsed = now - lastStatusMs;
    lastStatusMs = now;
    CaptureStats s = snapshot();
    printHealth(s, s.bytes - previousBytes, elapsed);
    previousBytes = s.bytes;
  }
  if ((uint32_t)(now - lastTxMs) >= LORA_PERIOD_MS) {
    lastTxMs = now;
    sendHealth(snapshot());
  }
  delay(5);
}
