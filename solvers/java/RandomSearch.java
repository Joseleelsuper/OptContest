final class RandomSearch {
    static void solve(Core s) {
        int[] q = s.reference.clone();
        s.evaluate(q, s.n, 0);
        if (s.n < 2) return;
        while (s.active()) { s.randomize(q); s.evaluate(q, s.n, 0); }
    }
}
