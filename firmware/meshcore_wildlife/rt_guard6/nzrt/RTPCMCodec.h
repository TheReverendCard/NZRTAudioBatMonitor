#pragma once
#include <algorithm>
#include <cstdint>
#include <cstddef>
// RTPCM1: lossless PCM16 blocks. Header "RTB1", LE uint32 sample count.
// Each <=256-sample block: LE int16 minimum, uint8 width (0..16), then
// unsigned offsets packed least-significant bit first, padded to a byte.
namespace RTPCMCodec {
constexpr size_t BLOCK=256, MAX_SAMPLES=384000;
inline unsigned bounds(const int16_t* pcm,size_t n,int16_t& minimum) {
 int16_t maximum=pcm[0];minimum=pcm[0];
 for(size_t i=1;i<n;++i){minimum=std::min(minimum,pcm[i]);maximum=std::max(maximum,pcm[i]);}
 uint32_t range=int32_t(maximum)-int32_t(minimum);unsigned width=0;
 while(range){++width;range>>=1;}return width;
}
inline size_t encodedSize(const int16_t* pcm,size_t n) {
 if(!pcm || !n || n>MAX_SAMPLES)return 0;
 size_t bytes=8;
 for(size_t at=0;at<n;at+=BLOCK){size_t count=std::min(BLOCK,n-at);int16_t minimum;unsigned width=bounds(pcm+at,count,minimum);bytes+=3+(count*width+7)/8;}
 return bytes;
}
inline size_t encode(const int16_t* pcm,size_t n,uint8_t* output,size_t capacity) {
 size_t needed=encodedSize(pcm,n);if(!needed || !output || needed>capacity)return 0;
 output[0]='R';output[1]='T';output[2]='B';output[3]='1';
 for(unsigned i=0;i<4;++i)output[4+i]=uint8_t(n>>(8*i));
 size_t pos=8;
 for(size_t at=0;at<n;at+=BLOCK){
  size_t count=std::min(BLOCK,n-at);int16_t minimum;unsigned width=bounds(pcm+at,count,minimum);
  output[pos++]=uint8_t(uint16_t(minimum));output[pos++]=uint8_t(uint16_t(minimum)>>8);output[pos++]=uint8_t(width);
  uint32_t pending=0;unsigned bits=0;
  for(size_t i=0;i<count;++i){
   uint32_t offset=uint32_t(int32_t(pcm[at+i])-int32_t(minimum));pending|=offset<<bits;bits+=width;
   while(bits>=8){output[pos++]=uint8_t(pending);pending>>=8;bits-=8;}
  }
  if(bits)output[pos++]=uint8_t(pending);
 }
 return pos;
}
}
