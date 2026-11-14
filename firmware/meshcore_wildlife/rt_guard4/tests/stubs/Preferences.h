#pragma once
#include "Arduino.h"
struct Preferences {
 bool begin(const char*,bool){return true;}void end(){}
 unsigned getUInt(const char*,unsigned n){return n;}size_t putUInt(const char*,unsigned){return 4;}
 bool getBool(const char*,bool b){return b;}size_t putBool(const char*,bool){return 1;}
 String getString(const char*,const char* s){return s;}size_t putString(const char*,const String&s){return s.size()+1;}void remove(const char*){}
};
