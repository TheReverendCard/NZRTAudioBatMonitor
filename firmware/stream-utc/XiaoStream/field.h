#pragma once
#include <stdint.h>
#include <math.h>
#include <time.h>
namespace field {
constexpr char modelSha[]="f9f857b24d21666831e3d5eaa145904003fc2cb0a93a64e59d0f68f4eb69588e";
// Same site and NOAA fractional-year approximation as the 1.0.6 field recorder.
// Return seconds until listening should resume. Zero means keep listening.
inline int64_t daytimeRemaining(int64_t epoch) {
    if (epoch < 1735689600 || epoch >= 4102444800LL) return 0;
    const int64_t day = (epoch + 12*3600) / 86400 * 86400;
    time_t t = time_t(day);
    struct tm utc{};
    gmtime_r(&t, &utc);
    const double pi=3.141592653589793, lat=-35.75*pi/180, lon=174.27;
    double g=2*pi/365*utc.tm_yday;
    double eq=229.18*(0.000075+0.001868*cos(g)-0.032077*sin(g)-0.014615*cos(2*g)-0.040849*sin(2*g));
    double dec=0.006918-0.399912*cos(g)+0.070257*sin(g)-0.006758*cos(2*g)
              +0.000907*sin(2*g)-0.002697*cos(3*g)+0.00148*sin(3*g);
    double ha=acos(cos(90.833*pi/180)/(cos(lat)*cos(dec))-tan(lat)*tan(dec))*180/pi;
    if (!isfinite(ha)) return 0;
    int64_t rise=day+llround((720-4*(lon+ha)-eq)*60);
    int64_t start=day+llround((720-4*(lon-ha)-eq)*60)-20*60;
    return epoch>=rise && epoch<start ? start-epoch : 0;
}
}
