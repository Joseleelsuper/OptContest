final class Sa {
    static void solve(Core s) {
        int[] q = s.reference.clone(), candidate = q.clone();
        long value = s.evaluate(q, s.n, 0);
        if (s.n < 2 || value < 0) return;
        double initialTemperature = Math.max(1.0, 0.01 * value), temperature = initialTemperature;
        s.setPrefix(q, s.n);
        long iteration = 0;
        while (s.active()) {
            int i = s.rand(s.n), j = s.rand(s.n - 1);
            if (j >= i) ++j;
            s.insert(q, candidate, s.n, i, j);
            long cost = s.evaluate(candidate, s.n, Math.min(i, j));
            if (cost < 0) break;
            if (s.accept(value, cost, temperature)) { System.arraycopy(candidate, 0, q, 0, s.n); value = cost; s.setPrefix(q, s.n); }
            ++iteration;
            temperature *= 0.9995;
            if (iteration % 10000 == 0) temperature = initialTemperature;
        }
    }
}
