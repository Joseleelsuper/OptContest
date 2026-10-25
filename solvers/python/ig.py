import numpy as np


def solve(s):
    q = s.reference.copy()
    if s.n < 2:
        s.evaluate(q, s.n, 0)
        return
    order = np.arange(s.n, dtype=np.int64)
    totals = np.zeros(s.n, dtype=np.int64)
    for i in range(s.n):
        for j in range(s.m):
            totals[i] += s.p[i, j]
    for i in range(1, s.n):
        job, j = order[i], i
        while j > 0 and totals[order[j - 1]] > totals[job]:
            order[j] = order[j - 1]
            j -= 1
        order[j] = job
    value = s.greedy(q, 0, order, s.n)
    if value < 0:
        return
    s.set_initial(q, value)
    value = s.local(q, value)
    temperature = max(1.0, 0.01 * s.initial_cost)
    candidate = q.copy()
    removed = np.empty(s.n, dtype=np.int64)
    marked = np.empty(s.n, dtype=np.bool_)
    count = min(6, s.n)
    stale = 0
    while s.active():
        previous_best = s.best_cost
        s.randomize(order)
        marked[:] = False
        for k in range(count):
            marked[order[k]] = True
            removed[k] = q[order[k]]
        length = 0
        for k in range(s.n):
            if not marked[k]:
                candidate[length] = q[k]
                length += 1
        cost = s.greedy(candidate, length, removed, count)
        if cost < 0:
            break
        cost = s.local(candidate, cost)
        if s.accept(value, cost, temperature):
            q[:] = candidate
            value = cost
        stale = 0 if s.best_cost < previous_best else stale + 1
        if stale == 200 and s.active():
            s.randomize(q)
            value = s.evaluate(q, s.n, 0)
            if value < 0:
                break
            value = s.local(q, value)
            stale = 0
