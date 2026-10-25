#pragma once
#include "core.hpp"

inline void local_search(Search& s) {
    auto q = s.reference;
    auto value = s.evaluate(q, s.n, 0);
    if (s.n < 2 || value < 0) return;
    while (s.active()) {
        s.local(q, value);
        if (!s.active()) break;
        s.randomize(q);
        value = s.evaluate(q, s.n, 0);
    }
}
