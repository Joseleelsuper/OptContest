import java.util.Arrays;

final class Ig {
    static void solve(Core s) {
        int[] q = s.reference.clone();
        if (s.n < 2) { s.evaluate(q, s.n, 0); return; }
        int[] order = new int[s.n], removed = new int[s.n];
        long[] totals = new long[s.n];
        for (int i = 0; i < s.n; ++i) { order[i] = i; for (int j = 0; j < s.m; ++j) totals[i] += s.p[i][j]; }
        for (int i = 1; i < s.n; ++i) {
            int job = order[i], j = i;
            while (j > 0 && totals[order[j - 1]] > totals[job]) { order[j] = order[j - 1]; --j; }
            order[j] = job;
        }
        long value = s.greedy(q, 0, order, s.n);
        if (value < 0) return;
        s.setInitial(q, value);
        value = s.local(q, value);
        double temperature = Math.max(1.0, 0.01 * s.initialCost);
        int[] candidate = q.clone();
        boolean[] marked = new boolean[s.n];
        int count = Math.min(6, s.n), stale = 0;
        while (s.active()) {
            long previousBest = s.bestCost;
            s.randomize(order);
            Arrays.fill(marked, false);
            for (int k = 0; k < count; ++k) { marked[order[k]] = true; removed[k] = q[order[k]]; }
            int length = 0;
            for (int k = 0; k < s.n; ++k) if (!marked[k]) candidate[length++] = q[k];
            long cost = s.greedy(candidate, length, removed, count);
            if (cost < 0) break;
            cost = s.local(candidate, cost);
            if (s.accept(value, cost, temperature)) { System.arraycopy(candidate, 0, q, 0, s.n); value = cost; }
            stale = s.bestCost < previousBest ? 0 : stale + 1;
            if (stale == 200 && s.active()) {
                s.randomize(q);
                value = s.evaluate(q, s.n, 0);
                if (value < 0) break;
                value = s.local(q, value);
                stale = 0;
            }
        }
    }
}
