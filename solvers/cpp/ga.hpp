#pragma once
#include "core.hpp"
#include <array>

inline void ga(Search& s) {
    std::vector<Sequence> population(32, Sequence(s.n)), following = population;
    std::array<Cost, 32> costs{}, next_costs{};
    std::vector<bool> used(s.n);
    population[0] = s.reference;
    for (int k = 0; k < 32; ++k) {
        if (k) s.randomize(population[k]);
        costs[k] = s.evaluate(population[k], s.n, 0);
        if (costs[k] < 0) { s.set_initial(s.best, s.best_cost); return; }
    }
    int elite = int(std::min_element(costs.begin(), costs.end()) - costs.begin());
    s.set_initial(population[elite], costs[elite]);
    if (s.n < 2) return;
    while (s.active()) {
        following[0] = population[elite];
        next_costs[0] = costs[elite];
        for (int k = 1; k < 32; ++k) {
            int a = s.rand(32), b = s.rand(32);
            for (int t = 0; t < 2; ++t) { int c = s.rand(32); if (costs[c] < costs[a]) a = c; }
            for (int t = 0; t < 2; ++t) { int c = s.rand(32); if (costs[c] < costs[b]) b = c; }
            auto [i, j] = s.positions();
            if (i > j) std::swap(i, j);
            std::fill(used.begin(), used.end(), false);
            for (int pos = i; pos <= j; ++pos) { int job = population[a][pos]; following[k][pos] = job; used[job] = true; }
            int dest = (j + 1) % s.n;
            for (int offset = 0; offset < s.n; ++offset) {
                int job = population[b][(j + 1 + offset) % s.n];
                if (!used[job]) { following[k][dest] = job; dest = (dest + 1) % s.n; }
            }
            if (s.uniform() < 0.2) {
                auto [from, to] = s.positions();
                int job = following[k][from];
                if (from < to) for (int pos = from; pos < to; ++pos) following[k][pos] = following[k][pos + 1];
                else for (int pos = from; pos > to; --pos) following[k][pos] = following[k][pos - 1];
                following[k][to] = job;
            }
            next_costs[k] = s.evaluate(following[k], s.n, 0);
            if (next_costs[k] < 0) return;
        }
        population.swap(following);
        costs.swap(next_costs);
        elite = int(std::min_element(costs.begin(), costs.end()) - costs.begin());
    }
}
