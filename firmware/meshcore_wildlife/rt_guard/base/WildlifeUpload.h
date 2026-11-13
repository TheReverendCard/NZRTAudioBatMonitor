// NZRT_JOURNAL_V2
#pragma once
// Called only by WildlifeTime's main-loop tick while its network is idle.
// No changes to microphone pins, detector thresholds or scoring.
#include <HTTPClient.h>
#include <WiFi.h>
#include <SPIFFS.h>
#include "WildlifeMic.h"
#include "WildlifeML.h"
#include "WildlifeJournal.h"
#include "WildlifeUploadConfig.h"

namespace WildlifeMic {
bool hasLiveEvents();
size_t formatLiveBatch(char* buf,size_t capacity);
void ackLiveBatch(size_t count);
}
namespace WildlifeML {bool testUploadDue();}
namespace WildlifeUpload {
static bool connecting = false;
enum class Purpose {Snapshot, Live, ML};
static Purpose purpose=Purpose::Snapshot;
static uint32_t lastLiveAttempt=0,liveDelay=0;
static char liveBody[4096];
static bool wasStandby = false;
static uint32_t nextAttempt = 0, connectStart = 0;
static constexpr uint32_t RETRY_MS = 15UL*60UL*1000UL;
static constexpr uint32_t SUCCESS_MS = 60UL*60UL*1000UL;

static void finish(bool ok) {
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  connecting = false;
  nextAttempt = millis() + (ok ? SUCCESS_MS : RETRY_MS);
  Serial.printf("NZRT WIFI_LOG result=%s retry_in_s=%lu retained_on_device=1\n",
      ok ? "ACK" : "FAILED", (unsigned long)((ok ? SUCCESS_MS : RETRY_MS)/1000));
}

static bool send(uint32_t utc) {
  const auto& health=WildlifeJournal::stats();
  // Historical readFault remains a diagnostic, not a veto on newer healthy logs.
  // Writer must have successfully read back a recent append during this boot.
  if(!health.verified || (uint32_t)(millis()-health.lastOK)>600000UL) {
    Serial.println("NZRT WIFI_LOG journal_not_fresh; withholding_success");
    WildlifeJournal::status();return false;
  }
  WildlifeJournal::Reader f;
  if(!f.good() || !f.size() || f.size()>8UL*1024UL*1024UL) {
    Serial.println("NZRT WIFI_LOG no_usable_journal_or_over_8MB");
    return false;
  }
  // Main-loop logging is not concurrent with this function. Hash a bounded,
  // whole-line prefix; native log bytes stay intact and are never erased.
  size_t size=f.size(), seen=0, boundary=0;
  uint32_t hash=2166136261UL, boundaryHash=hash;
  uint8_t buf[1024];
  while(seen<size) {
    size_t want=(size-seen)>sizeof(buf)?sizeof(buf):(size-seen);
    size_t n=f.readBytes((char*)buf,want);
    if(n!=want) {f.close();return false;}
    for(size_t i=0;i<n;++i) {
      hash=(hash^buf[i])*16777619UL;
      if(buf[i]=='\n') {boundary=seen+i+1;boundaryHash=hash;}
    }
    seen+=n;
    delay(1);
  }
  if(!boundary || !f.good()) {f.close();return false;}
  f.rewind();
  char hex[9], device[13], stamp[16];
  snprintf(hex,sizeof(hex),"%08lx",(unsigned long)boundaryHash);
  snprintf(device,sizeof(device),"%012llx",(unsigned long long)ESP.getEfuseMac());
  snprintf(stamp,sizeof(stamp),"%lu",(unsigned long)utc);
  WiFiClient client;
  HTTPClient http;
  http.setConnectTimeout(2000);
  http.setTimeout(8000);
  if(!http.begin(client,String(NZRT_UPLOAD_URL)+"/rt-log")) {f.close();return false;}
  http.addHeader("Authorization",String("Bearer ")+NZRT_UPLOAD_TOKEN);
  http.addHeader("Content-Type","application/octet-stream");
  http.addHeader("X-Name",String(device)+".txt");
  http.addHeader("X-Device",device);
  http.addHeader("X-FNV1a",hex);
  http.addHeader("X-Snapshot-UTC",stamp);
  http.addHeader("X-Firmware","NZRT-J4-PASS-1");
  int code=http.sendRequest("POST",&f,boundary);
  bool ok=code==200 && http.getString()==String("OK ")+hex;
  http.end(); f.close();
  return ok;
}

static bool sendLive(uint32_t utc) {
  size_t count=WildlifeMic::formatLiveBatch(liveBody,sizeof(liveBody));
  size_t bytes=strlen(liveBody);
  if(!bytes)return true;
  uint32_t hash=2166136261u;
  for(size_t i=0;i<bytes;++i)hash=(hash^uint8_t(liveBody[i]))*16777619u;
  char hex[9],device[13];
  snprintf(hex,sizeof(hex),"%08lx",(unsigned long)hash);
  snprintf(device,sizeof(device),"%012llx",(unsigned long long)ESP.getEfuseMac());
  WiFiClient client;
  HTTPClient http;
  http.setConnectTimeout(2000);
  http.setTimeout(8000);
  if(!http.begin(client,String(NZRT_UPLOAD_URL)+"/rt-log"))return false;
  http.addHeader("Authorization",String("Bearer ")+NZRT_UPLOAD_TOKEN);
  http.addHeader("Content-Type","application/octet-stream");
  http.addHeader("X-Name",String(device)+".txt");
  http.addHeader("X-Device",device);
  http.addHeader("X-FNV1a",hex);
  http.addHeader("X-Snapshot-UTC",String((unsigned long)utc));
  http.addHeader("X-Firmware","NZRT-J4-PASS-1");
  int code=http.POST((uint8_t*)liveBody,bytes);
  bool ok=code==200 && http.getString()==String("OK ")+hex;
  Serial.printf("NZRT HTTP route=/rt-log candidates=%u code=%d ack_match=%d\n",unsigned(count),code,ok);
  http.end();
  if(ok)WildlifeMic::ackLiveBatch(count);
  return ok;
}
static void finishLive(bool ok) {
  lastLiveAttempt=millis();
  liveDelay=ok?5000UL:30000UL;
  Serial.printf("NZRT LIVE result=%s retry_min_ms=%lu\n",ok?"ACK":"FAILED",(unsigned long)liveDelay);
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  connecting=false;
}

static bool tick(const String& ssid, const String& password, uint32_t utc) {
  if(!strlen(NZRT_UPLOAD_URL) || !strlen(NZRT_UPLOAD_TOKEN) || !ssid.length()) return false;
  bool standby=WildlifeMic::daytimeStandby();
  if(!standby) wasStandby=false;
  else if(!wasStandby) {wasStandby=true;nextAttempt=millis()+60000UL;}
  if(utc<1760000000UL) return false;
  if(connecting) {
    if(WiFi.status()==WL_CONNECTED) {
      if(purpose==Purpose::Live)finishLive(sendLive(utc));
      else if(purpose==Purpose::ML) {
        WildlifeML::connected();WiFi.disconnect(true);WiFi.mode(WIFI_OFF);connecting=false;
      } else {finish(send(utc));}
      return true;
    }
    if(millis()-connectStart>=12000UL) {
      Serial.printf("NZRT WIFI association_timeout status=%d\n",int(WiFi.status()));
      if(purpose==Purpose::Live)finishLive(false);
      else if(purpose==Purpose::ML) {WildlifeML::networkFailed();WiFi.disconnect(true);WiFi.mode(WIFI_OFF);connecting=false;}
      else finish(false);
    }
    return true;
  }
  // Due journal snapshots take precedence over optional clip transfers.
  bool journalDue=standby && (int32_t)(millis()-nextAttempt)>=0;
  bool mlDue=WildlifeML::wantsNetwork();
  bool liveDue=WildlifeMic::hasLiveEvents() && millis()-lastLiveAttempt>=liveDelay;
  if(!journalDue&&!liveDue&&!mlDue)return false;
  purpose=WildlifeML::testUploadDue()?Purpose::ML:(journalDue?Purpose::Snapshot:(liveDue?Purpose::Live:Purpose::ML));
  WiFi.mode(WIFI_STA);WiFi.setSleep(false);WiFi.begin(ssid.c_str(),password.c_str());
  connectStart=millis();connecting=true;
  Serial.println(purpose==Purpose::Live?"NZRT WIFI connecting purpose=CANDIDATE":purpose==Purpose::ML?"NZRT WIFI connecting purpose=ML":"NZRT WIFI_LOG connecting; daytime snapshot; audio journal retained");
  return true;
}
}

