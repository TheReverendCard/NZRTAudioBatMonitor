#pragma once
#include <cstdint>
#include <cstddef>
#include <cstdio>
#include <cstdarg>
#include <cstring>
#include <string>
#include <algorithm>
class Print {public:virtual ~Print(){};virtual size_t write(uint8_t)=0;virtual size_t write(const uint8_t*p,size_t n){size_t k=0;while(k<n&&write(p[k]))++k;return k;}size_t print(const char*s){return write((const uint8_t*)s,strlen(s));}size_t println(const char*s){return print(s)+print("\n");}size_t printf(const char* fmt,...){char b[4096];va_list a;va_start(a,fmt);int n=vsnprintf(b,sizeof(b),fmt,a);va_end(a);return n>0&&n<(int)sizeof(b)?write((uint8_t*)b,n):0;}};
class SerialT:public Print {public:using Print::write;std::string data;size_t write(uint8_t c)override{data+=(char)c;return 1;}};
extern SerialT Serial;
extern uint64_t fakeUs;
inline uint32_t millis(){return fakeUs/1000;}
inline void delay(unsigned n){fakeUs+=uint64_t(n)*1000;}

class String:public std::string {public:
 using std::string::string;String(){}String(const std::string& s):std::string(s){}String(unsigned long v):std::string(std::to_string(v)){}String(int v):std::string(std::to_string(v)){}
 bool startsWith(const char* x)const{return rfind(x,0)==0;}
 int indexOf(char c)const{auto p=find(c);return p==npos?-1:int(p);}
 String substring(size_t a)const{return substr(a);}String substring(size_t a,size_t b)const{return substr(a,b-a);}
 void trim(){auto a=find_first_not_of(" \r\n");if(a==npos){clear();return;}*this=substr(a,find_last_not_of(" \r\n")-a+1);}
};
struct ESPType{uint64_t getEfuseMac(){return 123;}};static ESPType ESP;

inline String operator+(const String& s,int n){return std::string(s)+std::to_string(n);}
