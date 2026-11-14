#pragma once
#include "Arduino.h"
class Stream:public Print {public:virtual int read()=0;virtual int peek()=0;virtual int available()=0;virtual void flush()=0;virtual size_t readBytes(char*p,size_t n){size_t i=0;while(i<n){int c=read();if(c<0)break;p[i++]=c;}return i;}};
