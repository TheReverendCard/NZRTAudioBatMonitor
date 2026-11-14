#include "WildlifeJournal.h"
#include <cassert>
#include <iostream>
SerialT Serial;Store store;FS SPIFFS;uint64_t fakeUs=0;
int main(){using namespace WildlifeJournal;
 {Writer w;assert(w);w.print("healthy\n");assert(w.close());}
 RtWatch::sig().audioPressure=true;{Writer w;assert(!w);}assert(stats().pressureDeferred==1);RtWatch::sig().audioPressure=false;
 store.corrupt=true;
 for(int i=0;i<3;++i){fakeUs+=31000000ULL;Writer w;assert(w);w.print("corrupt\n");assert(!w.close());}
 assert(stats().circuit.blocked(millis()));assert(stats().quarantined==2);
 auto previous=store.files;{Writer w;assert(!w);}assert(store.files==previous);
 char b[512];ramStatus(b,sizeof(b));assert(strstr(b,"reason=readback"));assert(diagnosticDue());diagnosticAck();assert(!diagnosticDue());
 store.corrupt=false;fakeUs+=901000000ULL;{Writer w;assert(w);w.print("recovered\n");assert(w.close());}
 assert(!stats().fault);assert(stats().errors==3);assert(stats().circuit.trips==1);assert(stats().quarantined==3);
 std::cout<<"GUARD3_JOURNAL_PASS corruption_circuit=1 no_writes_while_open=1 pressure_deferral=1 recovery=1 ram_diagnostics=1\n";
}
