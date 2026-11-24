#pragma once
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

namespace streamclock {
enum class Source { unknown, lora, ntp };
inline const char* name(Source s) {
    switch(s) {
        case Source::lora: return "LORA_OTD";
        case Source::ntp: return "WIFI_NTP";
        default: return "UNSYNCED";
    }
}
struct Anchor {
    int64_t up=0, utc=0;
    Source source=Source::unknown;
    int64_t at(int64_t ms) const { return source==Source::unknown ? 0 : utc+(ms-up); }
};
struct Beacon { uint32_t session=0, seq=0, epoch=0; };
inline bool number(const char* p,uint32_t& value) {
    if(!*p) return false;
    uint64_t n=0;
    for(;*p;++p) {
        if(*p<'0'||*p>'9') return false;
        n=n*10+(*p-'0');
        if(n>UINT32_MAX) return false;
    }
    value=static_cast<uint32_t>(n); return true;
}
inline bool validEpoch(int64_t seconds) { return seconds>=1735689600LL && seconds<4102444800LL; }
// Decode only the gateway send-time field from Museum Route 6 updates.
// Pages, acknowledgements and schedule/observation epochs are never clocks.
inline bool decode(char* packet,Beacon& b) {
    char* fields[13]={packet}; unsigned n=1;
    for(char* p=packet;*p;++p) if(*p=='|') {
        if(n==13) return false;
        *p=0; fields[n++]=p+1;
    }
    bool compact=n==10 && !strcmp(fields[0],"OTD3") && !strcmp(fields[4],"11000262") && !strcmp(fields[5],"6");
    bool extended=n==13 && !strcmp(fields[0],"OTD2") && !strcmp(fields[4],"6") && !strcmp(fields[6],"Whangarei Museum");
    if(!compact && !extended) return false;
    return number(fields[1],b.session) && b.session && number(fields[2],b.seq) && b.seq &&
           number(fields[3],b.epoch) && validEpoch(b.epoch);
}
// A retransmission cannot establish time. Require the next distinct update
// to advance in step with local elapsed time before trusting the gateway.
struct BeaconPair {
    Beacon last{}; int64_t lastUp=0;
    bool observe(Beacon b,int64_t up) {
        bool same=last.session==b.session;
        if(same && (b.seq<=last.seq || b.epoch<=last.epoch)) return false;
        int64_t elapsed=up-lastUp;
        int64_t delta=(int64_t(b.epoch)-last.epoch)*1000-elapsed;
        bool match=same && elapsed>=1000 && delta>=-4000 && delta<=4000;
        last=b; lastUp=up;
        return match;
    }
};
}
