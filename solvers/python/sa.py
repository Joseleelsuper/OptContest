def solve(s):
    q = s.reference.copy()
    candidate = q.copy()
    value = s.evaluate(q, s.n, 0)
    if s.n < 2 or value < 0:
        return
    initial_temperature = max(1.0, 0.01 * value)
    temperature = initial_temperature
    s.set_prefix(q, s.n)
    iteration = 0
    while s.active():
        i, j = s.positions()
        s.insert(q, candidate, s.n, i, j)
        cost = s.evaluate(candidate, s.n, min(i, j))
        if cost < 0:
            break
        if s.accept(value, cost, temperature):
            q[:] = candidate
            value = cost
            s.set_prefix(q, s.n)
        iteration += 1
        temperature *= 0.9995
        if iteration % 10000 == 0:
            temperature = initial_temperature
