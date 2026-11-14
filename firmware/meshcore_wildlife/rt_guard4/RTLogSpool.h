#pragma once
#include <cstdint>
#include <cstddef>
#include <cstring>
// Main-loop owned. Whole newline-terminated transactions are committed atomically.
// RAM is volatile. A matching HTTP ACK or a verified flash append is a durable copy.
namespace RTLogSpool {
class Queue {
 uint8_t* data=nullptr;size_t capacity=0;
 uint64_t first=0,last=0,ack=0;
 void put(uint64_t at,const void* p,size_t n){
  const uint8_t* b=static_cast<const uint8_t*>(p);
  while(n){size_t pos=at%capacity,take=n<capacity-pos?n:capacity-pos;memcpy(data+pos,b,take);b+=take;at+=take;n-=take;}
 }
 void get(uint64_t at,void* p,size_t n)const{
  uint8_t* b=static_cast<uint8_t*>(p);
  while(n){size_t pos=at%capacity,take=n<capacity-pos?n:capacity-pos;memcpy(b,data+pos,take);b+=take;at+=take;n-=take;}
 }
 uint32_t length(uint64_t at)const{uint32_t n=0;get(at,&n,4);return n;}
public:
 uint32_t committed=0,evicted=0,unconfirmedLost=0,flashSaved=0,acked=0,rejected=0;
 bool init(uint8_t* p,size_t cap){if(data)return true;if(!p||cap<8)return false;data=p;capacity=cap;return true;}
 size_t used()const{return size_t(last-first);}size_t availableCapacity()const{return capacity;}
 bool empty()const{return first==last;}bool pending()const{return ack<last;}
 bool push(const uint8_t* p,size_t n){
  if(!data||!n||n+4>capacity||n>65536||p[n-1]!='\n'){++rejected;return false;}
  while(used()+n+4>capacity){
   uint64_t end=first+4+length(first);++evicted;
   if(end>ack){++unconfirmedLost;ack=end;}
   first=end;
  }
  uint32_t len=uint32_t(n);put(last,&len,4);put(last+4,p,n);last+=n+4;++committed;return true;
 }
 // The caller can ACK only this exact snapshot after a content-hash match.
 size_t upload(uint8_t* out,size_t cap,uint64_t& token)const{
  uint64_t at=ack<first?first:ack;size_t bytes=0;token=at;
  while(at<last){uint32_t n=length(at);if(n>cap-bytes)break;get(at+4,out+bytes,n);bytes+=n;at+=4+n;token=at;}
  return bytes;
 }
 bool confirm(uint64_t token){
  if(token<ack||token>last)return false;
  uint64_t at=ack;
  while(at<token){at+=4+length(at);if(at>token)return false;}
  if(token>ack)++acked;ack=token;return true;
 }
 size_t oldest(uint8_t* out,size_t cap,uint64_t& token)const{
  token=first;if(empty())return 0;uint32_t n=length(first);if(n>cap)return 0;get(first+4,out,n);token=first+4+n;return n;
 }
 bool saved(uint64_t token){
  if(empty()||token!=first+4+length(first))return false;
  first=token;if(ack<first)ack=first;++flashSaved;return true;
 }
 void clear(){first=last=ack=0;}
};
}
