#include "WildlifeDay.h"
#include "WildlifeTime.h"
#include "WildlifeMic.h"
#include <cmath>
#include <ctime>
#include <cstdlib>
#include <SPIFFS.h>
#include <Preferences.h>

namespace WildlifeDay {
namespace {
// Approximate Maunu/Whangarei coordinate. Sunrise/sunset are computed per day.
// Later deployments elsewhere should configure site coordinates explicitly.
constexpr double LAT_DEG = -35.73;
constexpr double LON_DEG = 174.32;
constexpr double RADIANS = 3.14159265358979323846 / 180.0;
constexpr uint32_t CHECK_INTERVAL_MS = 30000UL;
constexpr uint32_t TEST_DURATION_MS = 90000UL;
// Wake 30 minutes BEFORE sunset; stop 30 minutes AFTER sunrise.
// This is microphone/I2S standby, NOT ESP32 deep/light sleep:
// the MeshCore LoRa radio, serial, and daily Wi-Fi time checks keep running.
constexpr double SUNRISE_GRACE_MIN = 30.0;
constexpr double SUNSET_LEAD_MIN = 30.0;
uint32_t lastCheckMs = 0;
double sunriseMin = 0;
double sunsetMin = 0;
bool knownTime = false;
bool solarValid = false;
int localMin = -1;
int localYday = -1;
int overrideMode = -1; // -1 automatic, 0 test wake, 1 test standby
uint32_t overrideUntil = 0;
bool initialized = false;
bool scheduleEnabled = true; // current BAT field-pilot default; configurable in NVS

bool nowPassed(uint32_t now, uint32_t due) {
  return static_cast<int32_t>(now-due) >= 0;
}
void journal(const char* what) {
  Serial.printf("NZRT DAY %s\n",what);
  File f=SPIFFS.open("/packet_log",FILE_APPEND);
  if(f){f.printf("NZRT DAY %s\n",what);f.close();}
}
void calculateSun(int dayOfYear, int utcOffsetHours) {
  // NOAA simplified equations of time and solar declination at local noon.
  // Astronomical approximation (~few minutes), not geolocation.
  double g = 2.0*3.14159265358979323846*(dayOfYear-1)/365.0;
  double eq = 229.18*(0.000075+0.001868*cos(g)-0.032077*sin(g)
               -0.014615*cos(2*g)-0.040849*sin(2*g));
  double dec=0.006918-0.399912*cos(g)+0.070257*sin(g)
             -0.006758*cos(2*g)+0.000907*sin(2*g)
             -0.002697*cos(3*g)+0.00148*sin(3*g);
  double lat=LAT_DEG*RADIANS;
  double z=90.833*RADIANS;
  double cosH=(cos(z)-sin(lat)*sin(dec))/(cos(lat)*cos(dec));
  solarValid=std::isfinite(cosH) && cosH > -1.0 && cosH < 1.0;
  if(!solarValid)return; // no valid solar boundaries: keep capture ON
  double ha=acos(cosH)/RADIANS;
  double noon=720.0-4.0*LON_DEG-eq+60.0*utcOffsetHours;
  sunriseMin=noon-4.0*ha;
  sunsetMin=noon+4.0*ha;
}
void test(int mode) {
  overrideMode=mode;
  overrideUntil=millis()+TEST_DURATION_MS;
  lastCheckMs=0;
  tick();
}
}
void begin() {
  // NZ DST: last Sunday in September at 02:00, first Sunday in April at 03:00.
  // This only affects formatting/sunrise calculations. RTC stays in UTC.
  setenv("TZ","NZST-12NZDT,M9.5.0/2,M4.1.0/3",1);
  tzset();
  Preferences prefs;
  if(prefs.begin("nzrt-day", true)) {
    scheduleEnabled=prefs.getBool("enabled",true);
    prefs.end();
  }
  initialized=true;
  lastCheckMs=0;
  Serial.printf("NZRT DAY schedule=%s site=WHANGAREI sunrise+30m/sunset-30m fail_open=ON meshcore=ON\n",
                scheduleEnabled?"ENABLED":"DISABLED");
}
void tick() {
  if(!initialized)return;
  uint32_t now=millis();
  if(lastCheckMs!=0 && now-lastCheckMs<CHECK_INTERVAL_MS)return;
  lastCheckMs=now;
  uint32_t utc=WildlifeTime::epochForUptime(now);
  knownTime=WildlifeTime::valid() && utc>1760000000UL;
  solarValid=false;
  localMin=-1;
  localYday=-1;
  bool shouldStandby=false;
  if(knownTime){
    // Arduino-ESP32 configTime() used for NTP can reset the global timezone.
    // Reapply NZ solar-site rules before converting UTC to local date/time.
    setenv("TZ","NZST-12NZDT,M9.5.0/2,M4.1.0/3",1);
    tzset();
    time_t u=static_cast<time_t>(utc);
    struct tm local={};
    if(localtime_r(&u,&local)){
      localYday=local.tm_yday+1;
      localMin=local.tm_hour*60+local.tm_min;
      calculateSun(localYday,local.tm_isdst>0?13:12);
      if(solarValid){
        shouldStandby=(localMin>=sunriseMin+SUNRISE_GRACE_MIN &&
                       localMin<sunsetMin-SUNSET_LEAD_MIN);
      }
    }
  }
  if(!scheduleEnabled) shouldStandby=false;
  if(overrideMode>=0){
    if(nowPassed(now,overrideUntil)){overrideMode=-1;}
    else shouldStandby=(overrideMode==1);
  }
  // An unknown or implausible clock always keeps ultrasonic monitoring on
  // outside an explicitly requested, 90-second hardware test.
  if(!knownTime && overrideMode<0) shouldStandby=false;
  WildlifeMic::setDaytimeStandby(shouldStandby);
}
void printStatus() {
  tick();
  uint32_t now=millis();
  uint32_t remain=overrideMode<0?0:(nowPassed(now,overrideUntil)?0:(overrideUntil-now)/1000UL);
  Serial.printf("NZRT DAY state=%s schedule_enabled=%d mode=%s clock=%s coord=Whangarei lat=%.2f lon=%.2f local_day=%d local_min=%d sunrise_min=%.1f sunset_min=%.1f override_left_s=%lu schedule=sunrise+30/sunset-30\n",
    WildlifeMic::daytimeStandby()?"STANDBY":"MONITORING",
    scheduleEnabled?1:0,
    overrideMode<0?"AUTO":(overrideMode?"TEST_SLEEP":"TEST_WAKE"),
    knownTime?(solarValid?"SYNCED":"SUN_UNAVAILABLE"):"UNSYNCED",
    LAT_DEG,LON_DEG,localYday,localMin,sunriseMin,sunsetMin,
    (unsigned long)remain);
}
void setScheduleEnabled(bool enabled) {
  if(scheduleEnabled!=enabled) {
    Preferences prefs;
    if(prefs.begin("nzrt-day",false)) {
      if(prefs.putBool("enabled",enabled)==0) {
        Serial.println("NZRT DAY ERROR: failed saving schedule setting");
        prefs.end();return;
      }
      prefs.end();
    } else {
      Serial.println("NZRT DAY ERROR: unable to open NVS");return;
    }
    scheduleEnabled=enabled;
  }
  overrideMode=-1;
  lastCheckMs=0;
  tick();
  Serial.printf("NZRT DAY schedule_enabled=%d persisted=1\n",enabled?1:0);
}
void testSleep() {test(1);}
void testWake() {test(0);}
void autoMode() {overrideMode=-1;lastCheckMs=0;tick();}
}
