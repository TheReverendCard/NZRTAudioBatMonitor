// CLI harness for native host parity testing. Input: 165 comma-separated floats per line.
// Output: one probability per line. Not an embedded deployment entrypoint.
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <sstream>
#include <string>
#include "inference_reference.h"
int main(){
  std::string line;
  while(std::getline(std::cin,line)){
    float x[nzrt::wav_mlp::kFeatures];
    std::stringstream ss(line);
    std::string part;
    for(size_t j=0;j<nzrt::wav_mlp::kFeatures;j++){
      if(!std::getline(ss,part,',')) {std::cerr<<"Expected 165 values\n";return 2;}
      char *end=nullptr;
      x[j]=std::strtof(part.c_str(),&end);
      if(!end || *end!='\0'){std::cerr<<"Not a numeric float\n";return 3;}
    }
    if(std::getline(ss,part,',')){std::cerr<<"Too many values\n";return 4;}
    float p=nzrt::wav_mlp::score(x);
    if(!std::isfinite(p)) {std::cerr<<"Nonfinite probability\n";return 5;}
    std::printf("%.9g\n",static_cast<double>(p));
  }
}
