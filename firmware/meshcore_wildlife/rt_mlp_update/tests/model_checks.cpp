#include <cassert>
#include <fstream>
#include <vector>
#include <iostream>
#include "RTModel.h"
int main(int argc,char**argv){
 std::ifstream f(argv[1],std::ios::binary);std::vector<uint8_t> b((std::istreambuf_iterator<char>(f)),{});
 RTModel::Model m,builtin;RTModel::builtin(builtin);assert(RTModel::valid(builtin));assert(RTModel::decode(b.data(),b.size(),m));
 assert(memcmp(m.values,builtin.values,sizeof(m.values))==0);assert(m.threshold==builtin.threshold);
 assert(!RTModel::decode(b.data(),b.size()-1,m));b[8]=2;assert(!RTModel::decode(b.data(),b.size(),m));b[8]=1;
 float x=NAN;memcpy(b.data()+24,&x,4);assert(!RTModel::decode(b.data(),b.size(),m));
 RTModel::builtin(m);m.values[165]=0;assert(!RTModel::valid(m));float features[165]={};features[0]=NAN;assert(!std::isfinite(RTModel::score(builtin,features)));
 std::cout<<"PASS numeric package equality, malformed schema/length/nonfinite/scale rejection\n";
}
