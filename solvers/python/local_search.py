def solve(s):
    q = s.reference.copy()
    value = s.evaluate(q, s.n, 0)
    if s.n < 2 or value < 0:
        return
    while s.active():
        s.local(q, value)
        if not s.active():
            break
        s.randomize(q)
        value = s.evaluate(q, s.n, 0)
