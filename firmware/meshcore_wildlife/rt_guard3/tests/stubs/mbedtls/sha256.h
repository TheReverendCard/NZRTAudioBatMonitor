#pragma once
#include <cstring>
inline int mbedtls_sha256_ret(const unsigned char*,size_t,unsigned char*o,int){memset(o,0,32);return 0;}
