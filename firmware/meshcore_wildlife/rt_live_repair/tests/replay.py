"""Exercise production DSP, queue and serialization against the existing HTTP receiver."""
from pathlib import Path
import sys, tempfile, subprocess, threading, urllib.request, urllib.error
here=Path(__file__).resolve().parents[1]
family=here.parent
sys.path.insert(0,str(family/'rt_mlp_update/tests'))
import receiver_baseline as receiver
sys.path.insert(0,str(family/'rt_mlp_update'))
from rt_log_reader import parse_logs

with tempfile.TemporaryDirectory() as temp:
    root=Path(temp)
    fake=root/'freertos'
    fake.mkdir()
    (fake/'FreeRTOS.h').write_text('')
    (fake/'portmacro.h').write_text('#define portMUX_TYPE int\n#define portMUX_INITIALIZER_UNLOCKED 0\n#define portENTER_CRITICAL(x)\n#define portEXIT_CRITICAL(x)\n')
    mic=(here/'payload/WildlifeMic.cpp').read_text()
    event_code=mic[mic.index('void formatEvent('):mic.index('bool begin()')]
    upload=(here/'payload/WildlifeUpload.h').read_text()
    send_code=upload[upload.index('static bool sendLive('):upload.index('static void finishLive(')]
    source=r"""
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cmath>
#include <string>
#include <map>
#include "WildlifeDetector.cpp"
namespace WildlifeTime {uint32_t epochForUptime(uint32_t ms){return 1794270000+ms/1000;} const char* source(){return "REPLAY";}}
namespace WildlifeMic {namespace {uint32_t sessionId=1;
""" + event_code + r"""
}
using std::size_t;
struct String : std::string {
 using std::string::string;
 String(const std::string& s):std::string(s){}
 explicit String(unsigned long n):std::string(std::to_string(n)){}
};
struct WiFiClient {};
struct Esp {uint64_t getEfuseMac(){return 0x123456abcdefull;}} ESP;
#define NZRT_UPLOAD_URL "http://localhost"
#define NZRT_UPLOAD_TOKEN "fixture"
std::map<std::string,std::string> headers;
int httpCode=503;bool goodHash=false;
struct HTTPClient {
 void setConnectTimeout(int){} void setTimeout(int){} void end(){}
 bool begin(WiFiClient&,const String& url){return url=="http://localhost/rt-log";}
 void addHeader(const String& name,const String& val){headers[name]=val;}
 int POST(uint8_t*,size_t){return httpCode;}
 String getString(){return goodHash?"OK "+headers["X-FNV1a"]:"wrong";}
};
char liveBody[4096];
""" + send_code + r"""
int main(){
 using namespace WildlifeDetector;
 reset(1,0);
 // Compare table transitions to individual MSB-first PDM bits through wraparound.
 uint32_t a=0,b=0,c=0,rng=0x6148;
 for(int i=0;i<100000;++i){
   rng=rng*1664525u+1013904223u;
   uint8_t v=rng>>24;
   for(int k=7;k>=0;--k){a+=((v>>k)&1)?1u:UINT32_MAX;b+=a;c+=b;}
   advanceByte(v);assert(a==cic_i1 && b==cic_i2 && c==cic_i3);
 }
 reset(1,0);
 for(int i=0;i<4;++i)onInputGap(1);
 assert(optionalHoldSamples==192000 && optionalClipHolds()==1);
 for(int i=0;i<192000;++i)processPcm(0);
 assert(!optionalHoldSamples && windows>0);
 reset(1,0);
 unsigned char block[2048];
 double err=0;
 // Physical-bit-rate sigma-delta replay of four 36 kHz pulses above quiet baseline.
 for(int blk=0;blk<1000;++blk){
   for(int i=0;i<2048;i+=2){
     unsigned word=0;
     for(int k=0;k<16;++k){
       int bit=(blk*1024+i/2)*16+k;
       double t=bit/3072000.0;
       bool pulse=t>=4 && t<4.33 && fmod(t-4,.08)<.006;
       double x=(pulse?.37:.0003)*sin(2*3.14159265358979*36000*t);
       err+=x;int out=err>=0?1:-1;err-=out;
       word=2*word+(out>0);
     }
     block[i]=word;block[i+1]=word>>8;
   }
   consume(block,sizeof(block),0);
 }
 Event e;assert(pop(e));assert(e.seq && e.features.bat_like && e.features.pulses>=3);
 WildlifeMic::queueLive(e);
 char batch[4096];assert(WildlifeMic::formatLiveBatch(batch,sizeof(batch))==1);
 assert(WildlifeMic::hasLiveEvents());fputs(batch,stdout);
 char retry[4096];WildlifeMic::formatLiveBatch(retry,sizeof(retry));assert(strcmp(batch,retry)==0);
 assert(!sendLive(1794270004));assert(WildlifeMic::liveCount==1);
 httpCode=200;assert(!sendLive(1794270004));assert(WildlifeMic::liveCount==1);
 goodHash=true;assert(sendLive(1794270004));assert(!WildlifeMic::hasLiveEvents());
 assert(headers["X-Device"]=="123456abcdef" && headers["X-Snapshot-UTC"]=="1794270004");
 assert(headers["Authorization"]=="Bearer fixture" && headers["X-Name"]=="123456abcdef.txt");
 strcpy(WildlifeMic::liveHealth,"NZRT FIELD health=1 state=STALLED\n");
 assert(WildlifeMic::hasLiveEvents() && sendLive(1794270004) && !WildlifeMic::hasLiveEvents());
 for(int i=0;i<70;++i){e.seq=i+1;WildlifeMic::queueLive(e);}
 assert(WildlifeMic::liveDropped==6 && WildlifeMic::liveCount==64);
 WildlifeMic::formatLiveBatch(batch,sizeof(batch));assert(strstr(batch," seq=7 "));
}
"""
    (root/'replay.cpp').write_text(source)
    subprocess.run(['c++','-std=c++11','-O2','-DNZRT_HOST_TEST','-I'+str(root),
        '-I'+str(here/'payload'),'-I'+str(family/'recovered_snapshot/nzrt'),
        str(root/'replay.cpp'),'-o',str(root/'replay')],check=True)
    body=subprocess.check_output([str(root/'replay')])
    server=receiver.Server(('127.0.0.1',0),root,['fixture'])
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        url=f'http://127.0.0.1:{server.server_port}/rt-log'
        digest=receiver.fnv(body)
        headers={'Authorization':'Bearer fixture','X-Name':'123456abcdef.txt','X-Device':'123456abcdef',
                 'X-FNV1a':digest,'X-Snapshot-UTC':'1794270004','X-Firmware':'NZRT-J4-LIVE-1'}
        for _ in range(2):
            with urllib.request.urlopen(urllib.request.Request(url,data=body,headers=headers)) as resp:
                assert resp.read()==('OK '+digest).encode()
        records=list((root/'RT').rglob('*.txt'))
        assert len(records)==1 and records[0].read_bytes()==body
        parsed=parse_logs([('live',body.decode()),('snapshot',body.decode())])
        assert len(parsed['events'])==1 and parsed['events'][0]['rt_class']=='bat_like'
        assert not parsed['conflicts'] and not parsed['unresolved']
        print(body.decode().strip())
        print('PASS: raw PDM replay, candidate queue, retry, checksum ACK and receiver file')
    finally:
        server.shutdown();server.server_close();thread.join()
