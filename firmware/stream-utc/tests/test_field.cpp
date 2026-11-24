#include <cassert>
#include "../XiaoStream/field.h"
int main() {
    assert(!field::daytimeRemaining(0));
    // 24 Nov 2026 00:00 UTC is early afternoon in Whangarei.
    const int64_t noon=1795478400;
    auto left=field::daytimeRemaining(noon);
    assert(left>5*3600 && left<9*3600);
    assert(field::daytimeRemaining(noon+left-1)==1);
    assert(!field::daytimeRemaining(noon+left));
    assert(!field::daytimeRemaining(noon+12*3600));
    // At winter local noon and midnight.
    assert(field::daytimeRemaining(1782000000)>0);
    assert(!field::daytimeRemaining(1782000000+12*3600));
}
