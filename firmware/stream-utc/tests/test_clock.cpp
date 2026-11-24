#include "../XiaoStream/stream_clock.h"
#include <cassert>
#include <cstdio>
using namespace streamclock;
static bool parse(const char* text, Beacon& b) {
    char packet[255]; snprintf(packet,sizeof packet,"%s",text); return decode(packet,b);
}
int main() {
    Beacon b; BeaconPair pair;
    assert(parse("OTD3|17|34|1795492800|11000262|6|1795499900|0|SCHED|1795492700",b));
    assert(b.epoch==1795492800 && !pair.observe(b,5000));
    assert(!pair.observe(b,9000));
    assert(parse("OTD2|17|35|1795492860|6|CW|Whangarei Museum|0|0|SCHED|0|0|0",b));
    assert(pair.observe(b,65000));
    assert(!parse("OTDACK|17|35|1795492900",b));
    assert(!parse("OTD3|17|35|42|11000262|6|0|0|SCHED|1795492800",b));
    assert(!parse("OTD3|17|35|1795492800|11000263|6|0|0|SCHED|1795492800",b));
    assert(!pair.observe({18,1,1795494000},66000));
    assert(!pair.observe({18,2,1795499000},67000));
    assert(pair.observe({18,3,1795499060},127000));
    Anchor a{4294999999LL,1795492800123,Source::ntp};
    assert(a.at(4294997499LL)==1795492797623 && a.at(4295000999LL)==1795492801123);
    assert(Anchor{}.at(100)==0);
}
