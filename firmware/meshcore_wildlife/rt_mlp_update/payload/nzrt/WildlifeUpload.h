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

namespace WildlifeUpload {
static bool connecting = false;
static bool forML = false;
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
  if(health.fault || !health.verified || (uint32_t)(millis()-health.lastOK)>600000UL) {
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
  http.addHeader("X-Firmware","NZRT-MLP-1-JOURNAL-2");
  int code=http.sendRequest("POST",&f,boundary);
  bool ok=code==200 && http.getString()==String("OK ")+hex;
  http.end(); f.close();
  return ok;
}

static bool tick(const String& ssid, const String& password, uint32_t utc) {
  if(!strlen(NZRT_UPLOAD_URL) || !strlen(NZRT_UPLOAD_TOKEN) || !ssid.length()) return false;
  bool standby=WildlifeMic::daytimeStandby();
  if(!standby) wasStandby=false;
  else if(!wasStandby) {wasStandby=true;nextAttempt=millis()+60000UL;}
  if(utc<1760000000UL) return false;
  if(connecting) {
    if(WiFi.status()==WL_CONNECTED) {
      if(forML) {
        WildlifeML::connected();WiFi.disconnect(true);WiFi.mode(WIFI_OFF);connecting=false;
      } else {finish(send(utc));}
      return true;
    }
    if(millis()-connectStart>=12000UL) {
      if(forML) {WildlifeML::networkFailed();WiFi.disconnect(true);WiFi.mode(WIFI_OFF);connecting=false;}
      else finish(false);
    }
    return true;
  }
  // Due journal snapshots take precedence over optional clip transfers.
  bool journalDue=standby && (int32_t)(millis()-nextAttempt)>=0;
  bool mlDue=WildlifeML::wantsNetwork();
  if(!journalDue&&!mlDue)return false;
  forML=!journalDue;
  WiFi.mode(WIFI_STA);WiFi.setSleep(false);WiFi.begin(ssid.c_str(),password.c_str());
  connectStart=millis();connecting=true;
  Serial.println(forML?"NZRT WIFI connecting purpose=ML":"NZRT WIFI_LOG connecting; daytime snapshot; audio journal retained");
  return true;
}
}
