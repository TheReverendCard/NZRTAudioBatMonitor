// NZRT_JOURNAL_V2
#include <Arduino.h>   // needed for PlatformIO
#include <Mesh.h>

#include "MyMesh.h"
#include "WildlifeMic.h"
#include "WildlifeTime.h"
#include "WildlifeDay.h"
#include "WildlifeJournal.h"

#ifdef DISPLAY_CLASS
  #include "UITask.h"
  static UITask ui_task(board, display);
#endif

#ifdef ETHERNET_ENABLED
  #define ETHERNET_CLI_BANNER "MeshCore Repeater CLI"
  #include <helpers/nrf52/EthernetCLI.h>
#endif

StdRNG fast_rng;
SimpleMeshTables tables;

MyMesh the_mesh(board, radio_driver, *new ArduinoMillis(), fast_rng, rtc_clock, tables);

void halt() {
  while (1) ;
}

static char command[160];
#ifdef ETHERNET_ENABLED
static char ethernet_command[160];
#endif

// For power saving
unsigned long POWERSAVING_FIRSTSLEEP_SECS = 120; // The first sleep (if enabled) from boot

#if defined(PIN_USER_BTN) && defined(_SEEED_SENSECAP_SOLAR_H_)
static unsigned long userBtnDownAt = 0;
#define USER_BTN_HOLD_OFF_MILLIS 1500
#endif

void setup() {
  Serial.begin(115200);
  delay(1000);

  board.begin();

#ifdef HAS_EXTERNAL_WATCHDOG
  external_watchdog.begin();
#endif

#if defined(MESH_DEBUG) && defined(NRF52_PLATFORM)
  // give some extra time for serial to settle so
  // boot debug messages can be seen on terminal
  delay(5000);
#endif

#ifdef DISPLAY_CLASS
  if (display.begin()) {
    display.startFrame();
    display.setCursor(0, 0);
    display.print("Please wait...");
    display.endFrame();
  }
#endif

  if (!radio_init()) {
    MESH_DEBUG_PRINTLN("Radio init failed!");
    halt();
  }

  fast_rng.begin(radio_driver.getRngSeed());

  FILESYSTEM* fs;
#if defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)
  InternalFS.begin();
  fs = &InternalFS;
  IdentityStore store(InternalFS, "");
#elif defined(ESP32)
  if(!SPIFFS.begin(false)) {
    Serial.println("NZRT JOURNAL ERROR mount_failed; filesystem NOT formatted; repair required");
    while(true) delay(1000);
  }
  fs = &SPIFFS;
  IdentityStore store(SPIFFS, "/identity");
#elif defined(RP2040_PLATFORM)
  LittleFS.begin();
  fs = &LittleFS;
  IdentityStore store(LittleFS, "/identity");
  store.begin();
#else
  #error "need to define filesystem"
#endif
  if (!store.load("_main", the_mesh.self_id)) {
    MESH_DEBUG_PRINTLN("Generating new keypair");
    the_mesh.self_id = radio_new_identity();   // create new random identity
    int count = 0;
    while (count < 10 && (the_mesh.self_id.pub_key[0] == 0x00 || the_mesh.self_id.pub_key[0] == 0xFF)) {  // reserved id hashes
      the_mesh.self_id = radio_new_identity(); count++;
    }
    store.save("_main", the_mesh.self_id);
  }

  Serial.print("Repeater ID: ");
  mesh::Utils::printHex(Serial, the_mesh.self_id.pub_key, PUB_KEY_SIZE); Serial.println();

  command[0] = 0;
#ifdef ETHERNET_ENABLED
  ethernet_command[0] = 0;
#endif

  sensors.begin();

  the_mesh.begin(fs);

  // Continuous audio sampling forbids sleep; MeshCore retains the radio.
  the_mesh.getNodePrefs()->powersaving_enabled = false;
  if (!WildlifeMic::begin())
    Serial.println("NZRT microphone start failed: MeshCore still running");
  WildlifeTime::begin(rtc_clock);
  WildlifeDay::begin();

#ifdef DISPLAY_CLASS
  ui_task.begin(the_mesh.getNodePrefs(), FIRMWARE_BUILD_DATE, FIRMWARE_VERSION);
#endif

#ifdef ETHERNET_ENABLED
  ethernet_start_task();
#endif

  // send out initial zero hop Advertisement to the mesh
#if ENABLE_ADVERT_ON_BOOT == 1
  the_mesh.sendSelfAdvertisement(16000, false);
#endif

  board.onBootComplete();
}

void loop() {
  // Handle Serial CLI
  int len = strlen(command);
  // `command` must stay NUL-terminated within its bounds. If it ever isn't,
  // strlen() above can return >= sizeof(command) and the loop below would then
  // index past the buffer, so clamp defensively.
  if (len >= (int)sizeof(command)) {
    command[0] = 0;
    len = 0;
  }
  static bool discardLine=false;
  while (Serial.available()) {
    char c=Serial.read();
    if(c=='\r' || c=='\n') {
      if(discardLine) {discardLine=false;len=0;command[0]=0;Serial.println("NZRT CLI rejected_overlong_line");break;}
      if(!len) continue; // absorb CRLF and empty lines
      command[len++]='\r';command[len]=0;break;
    }
    if(discardLine) continue;
    if(c=='\b' || c==127) {if(len)command[--len]=0;continue;}
    if(c==27) {len=0;command[0]=0;discardLine=true;continue;}
    if((unsigned char)c<32) continue;
    if(len >= (int)sizeof(command)-2) {len=0;command[0]=0;discardLine=true;continue;}
    command[len++]=c;command[len]=0;
    // Echo complete commands below, so secrets are never partially echoed.
  }

  if (len > 0 && command[len - 1] == '\r') {  // received complete line
    Serial.print('\n');
    command[len - 1] = 0;  // replace newline with C string null terminator
    if(strncmp(command,"nzrt wifi set ",14)!=0) Serial.println(command);
    char reply[160];
    reply[0] = 0;
#ifdef ETHERNET_ENABLED
    if (!ethernet_handle_command(command, reply)) {
      the_mesh.handleCommand(0, command, reply);
    }
#else
    if (strcmp(command,"log")==0) {
      strcpy(reply,WildlifeJournal::dump()?"   EOF":"ERROR: journal read failed");
    } else if (strcmp(command,"log erase")==0) {
      strcpy(reply,WildlifeJournal::erase()?"   log erased":"ERROR: log erase failed");
    } else if (strcmp(command,"nzrt journal")==0) {
      WildlifeJournal::status();
    } else if (strcmp(command,"nzrt journal test")==0) {
      WildlifeJournal::test();
    } else if (strcmp(command, "nzrt status") == 0) {
      WildlifeMic::printStatus();
    } else if (strcmp(command, "nzrt dsp on") == 0) {
      WildlifeMic::setDspEnabled(true);
    } else if (strcmp(command, "nzrt dsp off") == 0) {
      WildlifeMic::setDspEnabled(false);
    } else if (strcmp(command, "nzrt time") == 0) {
      WildlifeTime::printStatus();
    } else if (strncmp(command, "nzrt wifi set ", 14) == 0) {
      WildlifeTime::configureWiFi(command + 14);
    } else if (strcmp(command, "nzrt wifi clear") == 0) {
      WildlifeTime::clearWiFi();
    } else if (strcmp(command, "nzrt day") == 0) {
      WildlifeDay::printStatus();
    } else if (strcmp(command, "nzrt day test sleep") == 0) {
      WildlifeDay::testSleep();
    } else if (strcmp(command, "nzrt day test wake") == 0) {
      WildlifeDay::testWake();
    } else if (strcmp(command, "nzrt day auto") == 0) {
      WildlifeDay::autoMode();
    } else if (strcmp(command, "nzrt day enable") == 0) {
      WildlifeDay::setScheduleEnabled(true);
    } else if (strcmp(command, "nzrt day disable") == 0) {
      WildlifeDay::setScheduleEnabled(false);
    } else {
      the_mesh.handleCommand(0, command, reply);  // NOTE: there is no sender_timestamp via serial!
    }
#endif
    if (reply[0]) {
      Serial.print("  -> "); Serial.println(reply);
    }

    command[0] = 0;  // reset command buffer
  }

  WildlifeMic::printHealthIfDue();
  board.loop();   // let the board feed its watchdog, run periodic housekeeping

#ifdef ETHERNET_ENABLED
  ethernet_loop_maintain();
  if (ethernet_read_line(ethernet_command, sizeof(ethernet_command))) {
    char reply[160];
    reply[0] = 0;
    if (!ethernet_handle_command(ethernet_command, reply)) {
      the_mesh.handleCommand(0, ethernet_command, reply);
    }
    ethernet_send_reply(reply);
    ethernet_command[0] = 0;
  }
#endif

#if defined(PIN_USER_BTN) && defined(_SEEED_SENSECAP_SOLAR_H_) && !defined(DISPLAY_CLASS)
  // Hold the user button to power off the SenseCAP Solar repeater.
  int btnState = digitalRead(PIN_USER_BTN);
  if (btnState == LOW) {
    if (userBtnDownAt == 0) {
      userBtnDownAt = millis();
    } else if ((unsigned long)(millis() - userBtnDownAt) >= USER_BTN_HOLD_OFF_MILLIS) {
      Serial.println("Powering off...");
      board.powerOff();  // does not return
    }
  } else {
    userBtnDownAt = 0;
  }
#endif

  the_mesh.loop();
  sensors.loop();
#ifdef DISPLAY_CLASS
  ui_task.loop();
#endif
  rtc_clock.tick();
  WildlifeTime::tick(rtc_clock);
  WildlifeDay::tick();

#ifdef HAS_EXTERNAL_WATCHDOG
  external_watchdog.loop();
#endif
  if (the_mesh.getNodePrefs()->powersaving_enabled && !the_mesh.hasPendingWork()) {
#if defined(NRF52_PLATFORM)
    board.sleep(0); // nrf ignores seconds param, sleeps whenever possible
#else
    if (the_mesh.millisHasNowPassed(POWERSAVING_FIRSTSLEEP_SECS * 1000)) { // To check if it is time to sleep
      board.sleep(30); // Sleep. Wake up after a while or when receiving a LoRa packet
    }
#endif
  }
}
