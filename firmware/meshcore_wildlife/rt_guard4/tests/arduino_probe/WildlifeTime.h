#pragma once
#include <cstdint>
namespace WildlifeTime {inline uint32_t epochForUptime(uint32_t t){return 1794600000+t/1000;}inline const char* source(){return "TEST_ONLY";}inline bool valid(){return true;}inline bool compareNetworkIdle(){return true;}}
