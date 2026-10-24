#include "WildlifeTime.h"
#include <WiFi.h>
#include <Preferences.h>
#include <SPIFFS.h>
#include <time.h>
#include <cstring>
#include <cstdlib>
#include <sys/time.h>
#include <esp_sntp.h>

namespace WildlifeTime {
namespace {
// Connection and SNTP both have bounded, non-blocking timeouts.
// All functions except SNTP's callback execute from the ordinary MeshCore loop.
enum class NetState { UNCONFIGURED, PENDING, CONNECTING, WAIT_NTP, FINISHED };
NetState net = NetState::UNCONFIGURED;
String ssid;
String password;
uint32_t netStart = 0;
uint32_t nextAttemptAt = 0;
uint32_t attempts = 0;
uint32_t lastAttemptUptime = 0;
uint32_t lastSuccessUptime = 0;
uint32_t checkAt = 0;
uint32_t prevMeshEpoch = 0;
uint32_t prevMeshMillis = 0;
bool clockValid = false;
uint32_t epochAtSync = 0;
uint32_t millisAtSync = 0;
const char* clockSource = "UNSYNCED";
volatile bool sntpNotice = false;
mesh::RTCClock* rtcRef = nullptr;
constexpr uint32_t MIN_REASONABLE_EPOCH = 1760000000UL; // October 2025
constexpr uint32_t CONNECT_TIMEOUT_MS = 12000UL;
constexpr uint32_t NTP_TIMEOUT_MS = 12000UL;
constexpr uint32_t RESYNC_INTERVAL_MS = 24UL * 60UL * 60UL * 1000UL; // 24h after attempt ends
constexpr uint32_t BOOT_FIRST_ATTEMPT_MS = 3000UL;
bool timeDue(uint32_t now, uint32_t due) {
  return static_cast<int32_t>(now - due) >= 0;
}

void sntpCallback(struct timeval*) {
  // No Serial, filesystem, RTC updates or allocations in the network callback.
  sntpNotice = true;
}
void recordSync(const char* source, uint32_t epoch, uint32_t up) {
  if(epoch < MIN_REASONABLE_EPOCH) return;
  clockValid = true;
  epochAtSync = epoch;
  millisAtSync = up;
  clockSource = source;
  lastSuccessUptime = up;
  // Log every successful refresh, even if the correction is <3 seconds.
  // This makes the daily check observable and timestamps audit-friendly.
  Serial.printf("NZRT TIME_SYNC source=%s utc=%lu uptime_ms=%lu attempt=%lu\n",
                source,(unsigned long)epoch,(unsigned long)up,
                (unsigned long)attempts);
  File f = SPIFFS.open("/packet_log",FILE_APPEND);
  if(f) {
    f.printf("NZRT TIME_SYNC source=%s utc=%lu uptime_ms=%lu attempt=%lu\n",
             source,(unsigned long)epoch,(unsigned long)up,
             (unsigned long)attempts);
    f.close();
  }
}
void wifiOff() {
  // End the SNTP client too, to avoid unsupervised periodic network retries.
  // configTime() will initialise it again on our next deliberate attempt.
  if(net == NetState::WAIT_NTP) esp_sntp_stop();
  sntpNotice = false;
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  net=NetState::FINISHED;
  nextAttemptAt=millis()+RESYNC_INTERVAL_MS;
  Serial.printf("NZRT TIME wifi=OFF next_attempt_in_s=%lu\n",
                (unsigned long)(RESYNC_INTERVAL_MS/1000UL));
}
}
void begin(mesh::RTCClock& meshClock) {
  rtcRef=&meshClock;
  clockValid=false;
  clockSource="UNSYNCED";
  prevMeshEpoch=meshClock.getCurrentTime();
  prevMeshMillis=millis();
  attempts=0;
  lastAttemptUptime=0;
  lastSuccessUptime=0;
  nextAttemptAt=millis()+BOOT_FIRST_ATTEMPT_MS;
  sntpNotice=false;
  Preferences p;
  if(!p.begin("nzrt-time",true)) {
    Serial.println("NZRT TIME wifi=NVS_UNAVAILABLE; LoRa clock sync remains possible");
    net=NetState::UNCONFIGURED;
    return;
  }
  ssid=p.getString("ssid","");
  password=p.getString("pass","");
  p.end();
  net=ssid.length()?NetState::PENDING:NetState::UNCONFIGURED;
  Serial.printf("NZRT TIME wifi=%s clock=UNSYNCED (UTC, LoRa fallback uses authenticated remote 'clock sync')\n",
                net==NetState::PENDING?"CONFIGURED":"UNCONFIGURED");
}
void tick(mesh::RTCClock& meshClock) {
  uint32_t now=millis();
  // Existing MeshCore remote clock sync updates its RTC, not our UTC mapping.
  // Recognise only an abrupt, plausible forward clock correction. Ordinary
  // clock drift, adverts and messages from strangers do NOT set this clock.
  if(now-checkAt >= 1000UL) {
    checkAt=now;
    uint32_t meshNow=meshClock.getCurrentTime();
    uint32_t elapsed=(now-prevMeshMillis)/1000UL;
    if(meshNow>=MIN_REASONABLE_EPOCH &&
       static_cast<int64_t>(meshNow) -
       (static_cast<int64_t>(prevMeshEpoch)+elapsed) >= 30 &&
       !sntpNotice) {
      struct timeval tv = { static_cast<time_t>(meshNow), 0 };
      settimeofday(&tv,nullptr);
      recordSync("MESHCORE_REMOTE",meshNow,now);
    }
    prevMeshEpoch=meshNow;
    prevMeshMillis=now;
  }

  if(sntpNotice) {
    sntpNotice=false;
    // Ignore late SNTP callbacks after Wi-Fi has already been stopped.
    if(net != NetState::WAIT_NTP) return;
    time_t utc=time(nullptr);
    if(utc>=static_cast<time_t>(MIN_REASONABLE_EPOCH)) {
      meshClock.setCurrentTime(static_cast<uint32_t>(utc));
      prevMeshEpoch=meshClock.getCurrentTime();
      prevMeshMillis=now;
      recordSync("WIFI_NTP",static_cast<uint32_t>(utc),now);
      if(net==NetState::WAIT_NTP || net==NetState::CONNECTING)
        wifiOff();
    }
  }
  if(net==NetState::UNCONFIGURED) return;
  if(net==NetState::FINISHED) {
    // Single connection attempt every 24 hours, even after timeout.
    // No Wi-Fi activity in between, and MeshCore LoRa remains available.
    if(!timeDue(now,nextAttemptAt)) return;
    net=NetState::PENDING;
  }
  if(net==NetState::PENDING) {
    // Let the repeater and microphone finish initialisation first.
    if(!timeDue(now,nextAttemptAt)) return;
    ++attempts;
    lastAttemptUptime=now;
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);
    WiFi.begin(ssid.c_str(),password.c_str());
    netStart=now;
    net=NetState::CONNECTING;
    Serial.printf("NZRT TIME wifi=CONNECTING attempt=%lu\n",
                  (unsigned long)attempts);
    return;
  }
  if(net==NetState::CONNECTING) {
    if(WiFi.status()==WL_CONNECTED) {
      netStart=now;
      net=NetState::WAIT_NTP;
      sntpNotice=false;
      sntp_set_time_sync_notification_cb(sntpCallback);
      configTime(0,0,"pool.ntp.org","time.google.com");
      Serial.println("NZRT TIME wifi=CONNECTED ntp=WAITING");
    } else if(now-netStart>=CONNECT_TIMEOUT_MS) {
      Serial.println("NZRT TIME wifi=TIMEOUT fallback=MESHCORE_REMOTE");
      wifiOff();
    }
  } else if(net==NetState::WAIT_NTP &&
            now-netStart>=NTP_TIMEOUT_MS) {
    Serial.println("NZRT TIME ntp=TIMEOUT fallback=MESHCORE_REMOTE");
    wifiOff();
  }
}
uint32_t epochForUptime(uint32_t up) {
  if(!clockValid) return 0;
  int64_t delta=static_cast<int32_t>(up-millisAtSync);
  int64_t stamp=static_cast<int64_t>(epochAtSync)*1000LL+delta;
  return stamp>=static_cast<int64_t>(MIN_REASONABLE_EPOCH)*1000LL ?
         static_cast<uint32_t>(stamp/1000LL) : 0;
}
bool valid(){return clockValid;}
const char* source(){return clockSource;}
void printStatus() {
  const char* wifiStatus = net==NetState::UNCONFIGURED ? "NOT_CONFIGURED" :
        net==NetState::PENDING ? "PENDING" :
        net==NetState::CONNECTING ? "CONNECTING" :
        net==NetState::WAIT_NTP ? "WAIT_NTP" : "OFF";
  uint32_t now=millis();
  uint32_t dueSeconds=0;
  if(net==NetState::PENDING || net==NetState::FINISHED) {
    dueSeconds=timeDue(now,nextAttemptAt) ? 0 :
               ((nextAttemptAt-now)+999UL)/1000UL;
  }
  Serial.printf("NZRT TIME status=%s source=%s utc=%lu sync_uptime_ms=%lu wifi=%s attempts=%lu last_attempt_uptime_s=%lu last_sync_uptime_s=%lu next_wifi_attempt_in_s=%lu\n",
    clockValid?"SYNCED":"UNSYNCED",clockSource,
    (unsigned long)epochForUptime(now),
    (unsigned long)millisAtSync,wifiStatus,(unsigned long)attempts,
    (unsigned long)(lastAttemptUptime/1000UL),
    (unsigned long)(lastSuccessUptime/1000UL),
    (unsigned long)dueSeconds);
}
void configureWiFi(const char* args) {
  if(!args) {Serial.println("NZRT TIME ERROR: use nzrt wifi set SSID|PASSWORD");return;}
  const char* sep=strchr(args,'|');
  size_t n=sep?static_cast<size_t>(sep-args):0;
  if(!sep || n==0 || n>32 || strlen(sep+1)>63) {
    Serial.println("NZRT TIME ERROR: use SSID|PASSWORD (SSID up to 32 bytes, password up to 63)");
    return;
  }
  String newSSID=String(args).substring(0,n);
  String newPass=String(sep+1);
  Preferences p;
  if(!p.begin("nzrt-time",false)) {Serial.println("NZRT TIME ERROR NVS_OPEN");return;}
  bool saved=p.putString("ssid",newSSID)>0;
  // Empty password permitted for an explicitly open network.
  if(saved) saved=(newPass.length()==0||p.putString("pass",newPass)>0);
  p.end();
  if(saved) {
    ssid=newSSID;password=newPass;
    // Also permit provisioning without a reboot when previously unconfigured.
    if(net==NetState::UNCONFIGURED) {
      nextAttemptAt=millis()+BOOT_FIRST_ATTEMPT_MS;
      net=NetState::PENDING;
    }
    Serial.println("NZRT TIME Wi-Fi credentials stored locally (not in GitHub). Restart to sync.");
  } else Serial.println("NZRT TIME ERROR NVS_WRITE");
}
void clearWiFi() {
  Preferences p;
  if(p.begin("nzrt-time",false)) {
    p.remove("ssid");p.remove("pass");p.end();
  }
  ssid="";password="";
  if(net==NetState::CONNECTING||net==NetState::WAIT_NTP)wifiOff();
  net=NetState::UNCONFIGURED;
  Serial.println("NZRT TIME Wi-Fi credentials cleared");
}
}
