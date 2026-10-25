#pragma once
#include "ig.hpp"
#include <exception>
#include <thread>

inline unsigned worker_count = 0;

inline void parallel_ig(Search& s) {
    auto count = worker_count ? worker_count : std::max(1u, std::thread::hardware_concurrency());
    count = unsigned(std::min<Cost>(count, s.evaluation_limit));
    if (count == 1) { ig(s); return; }
    std::vector<Search> states;
    states.reserve(count);
    states.push_back(s);
    for (unsigned i = 1; i < count; ++i)
        states.emplace_back(s.n, s.m, s.p, s.next(), s.cpu_limit, s.evaluation_limit);
    std::vector<std::exception_ptr> errors(count);
    {
        std::vector<std::jthread> threads;
        threads.reserve(count);
        for (unsigned i = 0; i < count; ++i) {
            states[i].evaluation_limit = s.evaluation_limit / count + (i < s.evaluation_limit % count);
            // GetProcessTimes suma todos los hilos: comparten el mismo límite absoluto de CPU.
            threads.emplace_back([&, i] { try { ig(states[i]); } catch (...) { errors[i] = std::current_exception(); } });
        }
    }
    for (auto error : errors) if (error) std::rethrow_exception(error);
    s.initial = states[0].initial;
    s.initial_cost = states[0].initial_cost;
    s.evaluations = 0;
    s.checksum = 0;
    for (const auto& state : states) {
        s.evaluations += state.evaluations;
        s.checksum += state.checksum;
        if (state.best_cost < s.best_cost) { s.best_cost = state.best_cost; s.best = state.best; }
    }
}

inline int parallel_run(int argc, char** argv, bool contest = false) {
    try {
        int kept = 1;
        for (int i = 1; i < argc; ++i) {
            if (std::string(argv[i]) != "--threads") { argv[kept++] = argv[i]; continue; }
            if (++i == argc) throw std::runtime_error("Falta el número de hilos");
            std::string value = argv[i];
            if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos)
                throw std::runtime_error("Número de hilos incorrecto");
            auto parsed = std::stoul(value);
            if (parsed > 256) throw std::runtime_error("Máximo 256 hilos; 0 selecciona todos los disponibles");
            worker_count = unsigned(parsed);
        }
        return run(kept, argv, parallel_ig, "ig", contest);
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
