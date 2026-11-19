#pragma once
#include <cstdlib>
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_8BIT 2
inline void* heap_caps_malloc(size_t n,int){return malloc(n);}

#define MALLOC_CAP_INTERNAL 4

inline size_t heap_caps_get_free_size(int){return 1000000;}
inline size_t heap_caps_get_minimum_free_size(int){return 900000;}
inline size_t heap_caps_get_largest_free_block(int){return 800000;}
