import java.util.Arrays;

final class Ga {
    static void solve(Core s) {
        int[][] population = new int[32][s.n], following = new int[32][s.n];
        long[] costs = new long[32], nextCosts = new long[32];
        boolean[] used = new boolean[s.n];
        System.arraycopy(s.reference, 0, population[0], 0, s.n);
        for (int k = 0; k < 32; ++k) {
            if (k > 0) s.randomize(population[k]);
            costs[k] = s.evaluate(population[k], s.n, 0);
            if (costs[k] < 0) { s.setInitial(s.best, s.bestCost); return; }
        }
        int elite = 0;
        for (int k = 1; k < 32; ++k) if (costs[k] < costs[elite]) elite = k;
        s.setInitial(population[elite], costs[elite]);
        if (s.n < 2) return;
        while (s.active()) {
            System.arraycopy(population[elite], 0, following[0], 0, s.n);
            nextCosts[0] = costs[elite];
            for (int k = 1; k < 32; ++k) {
                int a = s.rand(32), b = s.rand(32);
                for (int t = 0; t < 2; ++t) { int c = s.rand(32); if (costs[c] < costs[a]) a = c; }
                for (int t = 0; t < 2; ++t) { int c = s.rand(32); if (costs[c] < costs[b]) b = c; }
                int i = s.rand(s.n), j = s.rand(s.n - 1);
                if (j >= i) ++j;
                if (i > j) { int temp = i; i = j; j = temp; }
                Arrays.fill(used, false);
                for (int pos = i; pos <= j; ++pos) { int job = population[a][pos]; following[k][pos] = job; used[job] = true; }
                int dest = (j + 1) % s.n;
                for (int offset = 0; offset < s.n; ++offset) {
                    int job = population[b][(j + 1 + offset) % s.n];
                    if (!used[job]) { following[k][dest] = job; dest = (dest + 1) % s.n; }
                }
                if (s.uniform() < 0.2) {
                    i = s.rand(s.n); j = s.rand(s.n - 1);
                    if (j >= i) ++j;
                    int job = following[k][i];
                    if (i < j) for (int pos = i; pos < j; ++pos) following[k][pos] = following[k][pos + 1];
                    else for (int pos = i; pos > j; --pos) following[k][pos] = following[k][pos - 1];
                    following[k][j] = job;
                }
                nextCosts[k] = s.evaluate(following[k], s.n, 0);
                if (nextCosts[k] < 0) return;
            }
            int[][] tempPopulation = population; population = following; following = tempPopulation;
            long[] tempCosts = costs; costs = nextCosts; nextCosts = tempCosts;
            elite = 0;
            for (int k = 1; k < 32; ++k) if (costs[k] < costs[elite]) elite = k;
        }
    }
}
