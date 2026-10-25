final class LocalSearch {
    static void solve(Core s) {
        int[] q = s.reference.clone();
        long value = s.evaluate(q, s.n, 0);
        if (s.n < 2 || value < 0) return;
        while (s.active()) {
            s.local(q, value);
            if (!s.active()) break;
            s.randomize(q);
            value = s.evaluate(q, s.n, 0);
        }
    }
}
