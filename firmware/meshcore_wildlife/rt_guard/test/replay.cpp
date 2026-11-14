// Little-endian float32 mono 192 kHz PCM on stdin. One process per profile/clip.
#include "WildlifeDetector.h"
#include <cstdio>
#include <cstdlib>
int main(int argc,char** argv){
 if(argc!=2 || !WildlifeDetector::requestPass(std::atoi(argv[1])))return 2;
 WildlifeDetector::reset(1,0);float pcm[3840];size_t n;
 while((n=std::fread(pcm,sizeof(float),3840,stdin))!=0){
  WildlifeDetector::consumePcmForTest(pcm,n);
  WildlifeDetector::Event e;
  while(WildlifeDetector::pop(e))std::printf("%u,%u,%u\n",unsigned(e.start_ms),unsigned(e.end_ms),unsigned(e.triggerMask));
 }
 if(std::ferror(stdin))return 3;
 WildlifeDetector::reset(2,0);
 WildlifeDetector::Event e;while(WildlifeDetector::pop(e))std::printf("%u,%u,%u\n",unsigned(e.start_ms),unsigned(e.end_ms),unsigned(e.triggerMask));
}
