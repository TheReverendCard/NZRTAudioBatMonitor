#pragma once
#include "Arduino.h"
#include <map>
#include <memory>
#define FILE_WRITE "w"
#define FILE_READ "r"
#define FILE_APPEND "a"
struct Store {std::map<std::string,std::string> files;bool shortWrite=false,corrupt=false,failOpen=false,failRename=false,failRemove=false;size_t other=0;};
extern Store store;
class File {std::string key;size_t pos=0;bool opened=false;public:File(){}File(const char*p,const char*m){key=p;if(store.failOpen)return;if(*m=='a'||*m=='w'){pos=store.files[key].size();opened=true;}else opened=store.files.count(key);}
File(const String&p,const char*m):File(p.c_str(),m){}
size_t readBytes(char*b,size_t n){return read((uint8_t*)b,n);}
operator bool()const{return opened;}size_t size()const{return opened?store.files[key].size():0;}bool seek(size_t p){pos=p;return opened&&p<=size();}int read(){return opened&&pos<size()?(uint8_t)store.files[key][pos++]:-1;}int peek(){return opened&&pos<size()?(uint8_t)store.files[key][pos]:-1;}
size_t read(uint8_t*b,size_t n){size_t i=0;for(;i<n;++i){int c=read();if(c<0)break;b[i]=c;}return i;}
size_t write(const uint8_t*b,size_t n){if(!opened)return 0;size_t k=store.shortWrite?n/2:n;store.files[key].append((const char*)b,k);return k;}
void flush(){if(store.corrupt&&size())store.files[key].back()='!';}void close(){opened=false;}
};
class FS {public:File open(const String&p,const char*m){return File(p.c_str(),m);}bool remove(const String&p){return remove(p.c_str());}File open(const char*p,const char*m){return File(p,m);}bool exists(const char*p){return store.files.count(p);}bool remove(const char*p){return !store.failRemove&&store.files.erase(p);}bool rename(const char*a,const char*b){if(store.failRename||!exists(a)||exists(b))return false;store.files[b]=store.files[a];store.files.erase(a);return true;}size_t totalBytes(){return 1438481;}size_t usedBytes(){size_t n=store.other;for(auto&p:store.files)n+=p.second.size();return n;}};
extern FS SPIFFS;
