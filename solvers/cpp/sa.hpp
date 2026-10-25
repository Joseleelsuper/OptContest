#pragma once
#include "core.hpp"

inline void sa(Search& s) {
    auto q = s.reference, candidate = q;
    auto value = s.evaluate(q, s.n, 0);
    if (s.n < 2 || value < 0) return;
    double initial_temperature = std::max(1.0, 0.01 * value), temperature = initial_temperature;
    s.set_prefix(q, s.n);
    Cost iteration = 0;
    while (s.active()) {
        auto [i, j] = s.positions();
        s.insert(q, candidate, s.n, i, j);
        auto cost = s.evaluate(candidate, s.n, std::min(i, j));
        if (cost < 0) break;
        if (s.accept(value, cost, temperature)) { q = candidate; value = cost; s.set_prefix(q, s.n); }
        ++iteration;
        temperature *= 0.9995;
        if (iteration % 10000 == 0) temperature = initial_temperature;
    }
}
