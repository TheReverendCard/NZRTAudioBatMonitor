#include "RTPCMCodec.h"
#include <fstream>
#include <vector>
#include <iterator>
#include <cassert>
int main(int argc,char** argv){
 assert(argc==3);std::ifstream f(argv[1],std::ios::binary);
 std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(f)),{});assert(bytes.size()%2==0);
 std::vector<int16_t> pcm(bytes.size()/2);
 for(size_t i=0;i<pcm.size();++i)pcm[i]=int16_t(uint16_t(bytes[2*i])|(uint16_t(bytes[2*i+1])<<8));
 size_t n=RTPCMCodec::encodedSize(pcm.data(),pcm.size());assert(n);
 std::vector<uint8_t> out(n+16,0xa5);assert(RTPCMCodec::encode(pcm.data(),pcm.size(),out.data(),n)==n);
 for(size_t i=n;i<out.size();++i)assert(out[i]==0xa5);
 assert(!RTPCMCodec::encode(pcm.data(),pcm.size(),out.data(),n-1));
 std::ofstream g(argv[2],std::ios::binary);g.write(reinterpret_cast<char*>(out.data()),n);
}
