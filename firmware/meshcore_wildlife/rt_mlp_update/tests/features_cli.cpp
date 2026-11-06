#include <fstream>
#include <iostream>
#include <vector>
#include <iomanip>
#include "RTFeatures.h"
#include "RTModel.h"
int main(int argc,char**argv){
 std::ifstream f(argv[1],std::ios::binary);std::vector<int16_t> audio;
 int16_t s;while(f.read((char*)&s,2))audio.push_back(s);
 std::vector<float> work(RTFeatures::WORK_FLOATS);float out[165];
 if(!RTFeatures::compute(audio.data(),audio.size(),work.data(),out))return 2;
 std::cout<<std::setprecision(12);for(float x:out)std::cout<<x<<" ";RTModel::Model m;RTModel::builtin(m);std::cout<<RTModel::score(m,out)<<"\n";
}
