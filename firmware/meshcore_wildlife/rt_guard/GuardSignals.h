#pragma once
#include "GuardPolicy.h"
#include <atomic>
namespace RtWatch {
// Function-local static in an inline function is shared across translation units.
struct Signals {
 std::atomic<uint32_t> rd{0},dp{0},win{0},rep{0},held{0},fault{0},previous{0};
 std::atomic<bool> forceLegacy{false}, ready{false},starting{false};
};
inline Signals& sig(){static Signals data;return data;}
inline void bump(std::atomic<uint32_t>& c){c.fetch_add(1,std::memory_order_relaxed);}
inline uint32_t val(const std::atomic<uint32_t>& c){return c.load(std::memory_order_relaxed);}
inline bool pressure(unsigned queued,unsigned capacity){
 return capacity && queued>=(capacity+1)/2;
}
}
