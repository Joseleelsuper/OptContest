def solve(s):
    q = s.reference.copy()
    s.evaluate(q, s.n, 0)
    if s.n < 2:
        return
    while s.active():
        s.randomize(q)
        s.evaluate(q, s.n, 0)
