#pragma once
#define NOMINMAX
#include <windows.h>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using Cost = std::int64_t;
using Sequence = std::vector<int>;

inline double cpu_time() {
    FILETIME created, exited, kernel, user;
    if (!GetProcessTimes(GetCurrentProcess(), &created, &exited, &kernel, &user))
        throw std::runtime_error("GetProcessTimes failed");
    auto ticks = [](FILETIME t) { return (std::uint64_t(t.dwHighDateTime) << 32) | t.dwLowDateTime; };
    return (ticks(kernel) + ticks(user)) / 10000000.0;
}

struct Search {
    int n, m;
    std::vector<Cost> p, prefix, sums, scratch;
    std::uint64_t state, checksum = 0;
    double cpu_limit;
    Cost evaluation_limit, evaluations = 0, reference_cost, best_cost, initial_cost;
    bool stopped = false;
    Sequence reference, best, initial;

    Search(int jobs, int machines, std::vector<Cost> processing, std::uint64_t seed, double cpu, Cost limit)
        : n(jobs), m(machines), p(std::move(processing)), prefix((n + 1) * m), sums(n + 1), scratch(m),
          state(seed), cpu_limit(cpu), evaluation_limit(limit), reference(n) {
        randomize(reference);
        reference_cost = cost(reference, n, 0);
        best = initial = reference;
        best_cost = initial_cost = reference_cost;
    }

    std::uint64_t next() {
        auto z = (state += 0x9E3779B97F4A7C15ULL);
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
        z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
        return z ^ (z >> 31);
    }
    int rand(int bound) {
        std::uint64_t b = bound, threshold = -b % b, value;
        do { value = next(); } while (value < threshold);
        return int(value % b);
    }
    double uniform() { return double(next() >> 11) * (1.0 / 9007199254740992.0); }
    void randomize(Sequence& q) {
        std::iota(q.begin(), q.end(), 0);
        for (int i = n - 1; i > 0; --i) { int j = rand(i + 1); std::swap(q[i], q[j]); }
    }
    bool active() {
        if (stopped || best_cost == 0) return false;
        if (evaluations >= evaluation_limit || (evaluations % 32 == 0 && cpu_time() >= cpu_limit)) stopped = true;
        return !stopped;
    }
    void set_prefix(const Sequence& q, int length) {
        for (int i = 0; i < length; ++i) {
            Cost left = 0;
            for (int j = 0; j < m; ++j) {
                left = std::max(prefix[i * m + j], left) + p[q[i] * m + j];
                prefix[(i + 1) * m + j] = left;
            }
            sums[i + 1] = sums[i] + left;
        }
    }
    Cost cost(const Sequence& q, int length, int start) {
        std::copy_n(prefix.begin() + start * m, m, scratch.begin());
        Cost total = sums[start];
        for (int i = start; i < length; ++i) {
            Cost left = 0;
            for (int j = 0; j < m; ++j) {
                left = std::max(scratch[j], left) + p[q[i] * m + j];
                scratch[j] = left;
            }
            total += left;
        }
        return total;
    }
    Cost evaluate(const Sequence& q, int length, int start) {
        if (!active()) return -1;
        Cost value = cost(q, length, start);
        ++evaluations;
        if (length == n) {
            checksum += std::uint64_t(value);
            if (value < best_cost) { best_cost = value; best = q; }
        }
        return value;
    }
    void set_initial(const Sequence& q, Cost value) {
        if (value >= 0) { initial = q; initial_cost = value; }
    }
    std::pair<int, int> positions() {
        int i = rand(n), j = rand(n - 1);
        if (j >= i) ++j;
        return {i, j};
    }
    void insert(const Sequence& q, Sequence& out, int length, int i, int j) {
        std::copy_n(q.begin(), length, out.begin());
        int job = q[i];
        if (i < j) for (int k = i; k < j; ++k) out[k] = out[k + 1];
        else for (int k = i; k > j; --k) out[k] = out[k - 1];
        out[j] = job;
    }
    Cost local(Sequence& q, Cost value) {
        Sequence candidate(n);
        while (active()) {
            set_prefix(q, n);
            bool improved = false;
            for (int i = 0; i < n && !improved; ++i) for (int j = 0; j < n; ++j) {
                if (i == j) continue;
                insert(q, candidate, n, i, j);
                Cost c = evaluate(candidate, n, std::min(i, j));
                if (c < 0) return value;
                if (c < value) { q = candidate; value = c; improved = true; break; }
            }
            if (improved) continue;
            for (int i = 0; i < n && !improved; ++i) for (int j = i + 1; j < n; ++j) {
                candidate = q;
                std::swap(candidate[i], candidate[j]);
                Cost c = evaluate(candidate, n, i);
                if (c < 0) return value;
                if (c < value) { q = candidate; value = c; improved = true; break; }
            }
            if (!improved) break;
        }
        return value;
    }
    Cost greedy(Sequence& q, int length, const Sequence& order, int count) {
        Sequence candidate(n), chosen(n);
        Cost value = -1;
        for (int k = 0; k < count; ++k) {
            set_prefix(q, length);
            Cost minimum = std::numeric_limits<Cost>::max();
            for (int pos = 0; pos <= length; ++pos) {
                std::copy_n(q.begin(), pos, candidate.begin());
                candidate[pos] = order[k];
                std::copy(q.begin() + pos, q.begin() + length, candidate.begin() + pos + 1);
                Cost c = evaluate(candidate, length + 1, pos);
                if (c < 0) return -1;
                if (c < minimum) { minimum = c; std::copy_n(candidate.begin(), length + 1, chosen.begin()); }
            }
            ++length;
            std::copy_n(chosen.begin(), length, q.begin());
            value = minimum;
        }
        return value;
    }
    bool accept(Cost old, Cost value, double temperature) {
        return value <= old || uniform() < std::exp(double(old - value) / temperature);
    }
};

inline std::vector<Cost> tokens(const std::string& line) {
    std::istringstream input(line);
    std::vector<Cost> values;
    Cost value;
    while (input >> value) values.push_back(value);
    if (!input.eof()) throw std::runtime_error("Entero incorrecto");
    return values;
}

inline std::string algorithm(int argc, char** argv) {
    for (int i = 1; i + 1 < argc; ++i) if (std::string(argv[i]) == "--algorithm") return argv[i + 1];
    return "ig";
}

inline int run(int argc, char** argv, void (*solve)(Search&), const std::string& selected, bool contest = false) {
    try {
        std::string path = "test.txt";
        std::random_device entropy;
        std::uint64_t seed = (std::uint64_t(entropy()) << 32) ^ entropy();
        double cpu = 57;
        Cost limit = std::numeric_limits<Cost>::max();
        bool has_cpu = false, has_limit = false;
        for (int i = 1; i < argc; ++i) {
            std::string flag = argv[i];
            if (flag == "--contest") { contest = true; continue; }
            if (++i >= argc) throw std::runtime_error("Falta el valor del argumento");
            std::string value = argv[i];
            std::size_t end = 0;
            if (flag == "--instance") path = value;
            else if (flag == "--algorithm") { if (value != selected) throw std::runtime_error("Algoritmo incorrecto"); }
            else if (flag == "--output") { if (value != "json") throw std::runtime_error("Salida incorrecta"); }
            else if (flag == "--cpu-budget") { cpu = std::stod(value, &end); has_cpu = true; }
            else if (flag == "--max-evaluations") { limit = std::stoll(value, &end); has_limit = true; }
            else if (flag == "--seed") {
                if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos) throw std::runtime_error("Semilla incorrecta");
                seed = std::stoull(value, &end);
            } else throw std::runtime_error("Argumento desconocido: " + flag);
            if (end && end != value.size()) throw std::runtime_error("Número incorrecto");
        }
        if (has_cpu && has_limit) throw std::runtime_error("Los límites son excluyentes");
        if (has_limit) cpu = 86400;
        if (!std::isfinite(cpu) || cpu <= 0 || limit < 1) throw std::runtime_error("Presupuesto incorrecto");
        std::ifstream file(path, std::ios::binary);
        if (!file) throw std::runtime_error("No se puede leer la instancia");
        std::string text((std::istreambuf_iterator<char>(file)), {});
        if (text.size() > 1048576) throw std::runtime_error("Archivo demasiado grande");
        if (text.starts_with("\xEF\xBB\xBF")) text.erase(0, 3);
        std::istringstream input(text);
        std::vector<std::vector<Cost>> lines;
        std::string line;
        while (std::getline(input, line)) { auto row = tokens(line); if (!row.empty()) lines.push_back(std::move(row)); }
        if (lines.empty() || lines[0].size() != 2) throw std::runtime_error("Cabecera esperada: n m");
        auto n = lines[0][0], m = lines[0][1];
        if (n < 1 || m < 1 || n > 10000 || m > 10000 || n * m > 10000 || lines.size() != std::size_t(n + 1))
            throw std::runtime_error("Dimensiones o filas incorrectas");
        std::vector<Cost> p;
        Cost maximum = 0;
        for (int i = 1; i <= n; ++i) {
            if (lines[i].size() != std::size_t(2 * m)) throw std::runtime_error("Fila incorrecta");
            for (int j = 0; j < m; ++j) {
                auto duration = lines[i][2 * j + 1];
                if (lines[i][2 * j] != j || duration < 0) throw std::runtime_error("Par máquina-duración incorrecto");
                p.push_back(duration);
                maximum = std::max(maximum, duration);
            }
        }
        if (maximum > std::numeric_limits<Cost>::max() / n / (n + m)) throw std::runtime_error("Posible desbordamiento int64");
        Search s(int(n), int(m), std::move(p), seed, cpu, limit);
        solve(s);
        auto print_sequence = [](const Sequence& q, bool json) {
            if (json) std::cout << '[';
            for (std::size_t i = 0; i < q.size(); ++i) { if (i) std::cout << (json ? "," : " "); std::cout << q[i] + 1; }
            if (json) std::cout << ']';
        };
        std::cout << std::setprecision(17);
        if (contest) {
            std::cout << double(s.best_cost) / n << '\n' << cpu_time() << '\n';
            print_sequence(s.best, false);
            std::cout << '\n';
        } else {
            std::cout << "{\"algorithm\":\"" << selected << "\",\"seed\":" << seed
                << ",\"reference_cost\":" << s.reference_cost << ",\"initial_cost\":" << s.initial_cost << ",\"cost\":" << s.best_cost
                << ",\"fmed_reference\":" << double(s.reference_cost) / n << ",\"fmed_initial\":" << double(s.initial_cost) / n
                << ",\"fmed_final\":" << double(s.best_cost) / n << ",\"reference_sequence\":";
            print_sequence(s.reference, true);
            std::cout << ",\"initial_sequence\":"; print_sequence(s.initial, true);
            std::cout << ",\"sequence\":"; print_sequence(s.best, true);
            std::cout << ",\"evaluations\":" << s.evaluations << ",\"cost_checksum\":" << s.checksum << ",\"cpu_seconds\":" << cpu_time() << "}\n";
        }
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
