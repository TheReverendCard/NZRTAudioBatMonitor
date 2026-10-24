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

void sntpCallback(struct timeval*) {
  // No Serial, filesystem, RTC updates or allocations in the network callback.
  sntpNotice = true;
}
void recordSync(const char* source, uint32_t epoch, uint32_t up) {
  if(epoch < MIN_REASONABLE_EPOCH) return;
  bool changed = !clockValid || strcmp(clockSource,source)!=0 ||
                 abs(static_cast<int32_t>(epoch - epochAtSync -
                   ((up - millisAtSync)/1000UL))) > 3;
  clockValid = true;
  epochAtSync = epoch;
  millisAtSync = up;
  clockSource = source;
  if(!changed) return;
  Serial.printf("NZRT TIME_SYNC source=%s utc=%lu uptime_ms=%lu\n",
                source,(unsigned long)epoch,(unsigned long)up);
  File f = SPIFFS.open("/packet_log",FILE_APPEND);
  if(f) {
    f.printf("NZRT TIME_SYNC source=%s utc=%lu uptime_ms=%lu\n",
             source,(unsigned long)epoch,(unsigned long)up);
    f.close();
  }
}
void wifiOff() {
  // Bluetooth and LoRa are unaffected; stop only the 2.4-GHz Wi-Fi radio.
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  net=NetState::FINISHED;
}
}
void begin(mesh::RTCClock& meshClock) {
  rtcRef=&meshClock;
  clockValid=false;
  clockSource="UNSYNCED";
  prevMeshEpoch=meshClock.getCurrentTime();
  prevMeshMillis=millis();
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
  if(net==NetState::UNCONFIGURED || net==NetState::FINISHED) return;
  if(net==NetState::PENDING) {
    // Let the repeater and microphone finish initialisation first.
    if(now<3000UL) return;
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);
    WiFi.begin(ssid.c_str(),password.c_str());
    netStart=now;
    net=NetState::CONNECTING;
    Serial.println("NZRT TIME wifi=CONNECTING");
    return;
  }
  if(net==NetState::CONNECTING) {
    if(WiFi.status()==WL_CONNECTED) {
      configTime(0,0,"pool.ntp.org","time.google.com");
      sntp_set_time_sync_notification_cb(sntpCallback);
      netStart=now;
      net=NetState::WAIT_NTP;
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
  Serial.printf("NZRT TIME status=%s source=%s utc=%lu sync_uptime_ms=%lu wifi=%s\n",
    clockValid?"SYNCED":"UNSYNCED",clockSource,
    (unsigned long)epochForUptime(millis()),
    (unsigned long)millisAtSync,wifiStatus);
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
