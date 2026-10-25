#pragma once
#include "core.hpp"

inline void random_search(Search& s) {
    auto q = s.reference;
    s.evaluate(q, s.n, 0);
    if (s.n < 2) return;
    while (s.active()) { s.randomize(q); s.evaluate(q, s.n, 0); }
}
