import numpy as np


def solve(s):
    population = np.empty((32, s.n), dtype=np.int64)
    following = np.empty_like(population)
    costs = np.empty(32, dtype=np.int64)
    next_costs = np.empty_like(costs)
    used = np.empty(s.n, dtype=np.bool_)
    population[0] = s.reference
    for k in range(32):
        if k:
            s.randomize(population[k])
        costs[k] = s.evaluate(population[k], s.n, 0)
        if costs[k] < 0:
            s.set_initial(s.best, s.best_cost)
            return
    elite = 0
    for k in range(1, 32):
        if costs[k] < costs[elite]:
            elite = k
    s.set_initial(population[elite], costs[elite])
    if s.n < 2:
        return
    while s.active():
        following[0] = population[elite]
        next_costs[0] = costs[elite]
        for k in range(1, 32):
            a, b = s.rand(32), s.rand(32)
            for _ in range(2):
                c = s.rand(32)
                if costs[c] < costs[a]:
                    a = c
            for _ in range(2):
                c = s.rand(32)
                if costs[c] < costs[b]:
                    b = c
            i, j = s.positions()
            if i > j:
                i, j = j, i
            used[:] = False
            for pos in range(i, j + 1):
                job = population[a, pos]
                following[k, pos] = job
                used[job] = True
            dest = (j + 1) % s.n
            for offset in range(s.n):
                job = population[b, (j + 1 + offset) % s.n]
                if not used[job]:
                    following[k, dest] = job
                    dest = (dest + 1) % s.n
            if s.uniform() < 0.2:
                i, j = s.positions()
                job = following[k, i]
                if i < j:
                    for pos in range(i, j):
                        following[k, pos] = following[k, pos + 1]
                else:
                    for pos in range(i, j, -1):
                        following[k, pos] = following[k, pos - 1]
                following[k, j] = job
            next_costs[k] = s.evaluate(following[k], s.n, 0)
            if next_costs[k] < 0:
                return
        population, following = following, population
        costs, next_costs = next_costs, costs
        elite = 0
        for k in range(1, 32):
            if costs[k] < costs[elite]:
                elite = k
