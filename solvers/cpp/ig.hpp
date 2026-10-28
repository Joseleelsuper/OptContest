#pragma once
#include "core.hpp"

template<int Destruction = 6, int TemperatureBps = 100, int Restart = 200>
inline void ig_search(Search& s) {
    static_assert(Destruction > 0 && TemperatureBps > 0 && Restart > 0);
    auto q = s.reference;
    if (s.n < 2) { s.evaluate(q, s.n, 0); return; }
    Sequence order(s.n), removed(s.n);
    std::vector<Cost> totals(s.n);
    std::iota(order.begin(), order.end(), 0);
    for (int i = 0; i < s.n; ++i) for (int j = 0; j < s.m; ++j) totals[i] += s.p[i * s.m + j];
    std::stable_sort(order.begin(), order.end(), [&](int a, int b) { return totals[a] < totals[b]; });
    auto value = s.greedy(q, 0, order, s.n);
    if (value < 0) return;
    s.set_initial(q, value);
    value = s.local(q, value);
    double temperature = std::max(1.0, (TemperatureBps / 10000.0) * s.initial_cost);
    auto candidate = q;
    std::vector<bool> marked(s.n);
    int count = std::min(Destruction, s.n), stale = 0;
    while (s.active()) {
        auto previous_best = s.best_cost;
        s.randomize(order);
        std::fill(marked.begin(), marked.end(), false);
        for (int k = 0; k < count; ++k) { marked[order[k]] = true; removed[k] = q[order[k]]; }
        int length = 0;
        for (int k = 0; k < s.n; ++k) if (!marked[k]) candidate[length++] = q[k];
        auto cost = s.greedy(candidate, length, removed, count);
        if (cost < 0) break;
        cost = s.local(candidate, cost);
        if (s.accept(value, cost, temperature)) { q = candidate; value = cost; }
        stale = s.best_cost < previous_best ? 0 : stale + 1;
        if (stale == Restart && s.active()) {
            s.randomize(q);
            value = s.evaluate(q, s.n, 0);
            if (value < 0) break;
            value = s.local(q, value);
            stale = 0;
        }
    }
}

inline void ig(Search& s) { ig_search(s); }
