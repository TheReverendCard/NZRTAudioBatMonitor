#include "../firmware/xiao_bat_overnight/ClockPolicy.h"
#include <cassert>
int main(){
  using namespace RecorderClock;
  uint32_t a=0,b=0;
  auto positive=interval(DAY,0.5,a,DAY);
  assert(positive>DAY && positive<=2*DAY);
  assert(interval(DAY,-0.5,b,DAY)==positive && a==b);
  assert(interval(30,0,a,DAY)==DAY);
  uint32_t zero=0;assert(interval(DAY,0,zero,DAY)==2*DAY);
  assert(interval(7*DAY,0,zero,7*DAY)<=MAX_INTERVAL);
  assert(interval(DAY,100,a,DAY)<DAY);
  assert(attemptAt(100,80,90,false,1,true)==990);
  assert(attemptAt(100,80,90,false,3,true)==86500);
  assert(attemptAt(100,200,90,true,3,true)==200);
}
