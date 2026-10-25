#include "random_search.hpp"
#include "local_search.hpp"
#include "sa.hpp"
#include "ga.hpp"
#include "ig.hpp"

int main(int argc, char** argv) {
    auto name = algorithm(argc, argv);
    void (*solve)(Search&) = name == "random" ? random_search : name == "local" ? local_search :
        name == "sa" ? sa : name == "ga" ? ga : name == "ig" ? ig : nullptr;
    if (!solve) { std::cerr << "Algoritmo desconocido\n"; return 1; }
    return run(argc, argv, solve, name);
}
