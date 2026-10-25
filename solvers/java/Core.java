import java.lang.management.ManagementFactory;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.SecureRandom;
import java.util.Locale;
import java.util.function.Consumer;

final class Core {
    static final com.sun.management.OperatingSystemMXBean OS =
        (com.sun.management.OperatingSystemMXBean) ManagementFactory.getOperatingSystemMXBean();
    final int n, m;
    final long[][] p, prefix;
    final long[] sums, scratch;
    long state, checksum, evaluations, referenceCost, bestCost, initialCost;
    final long evaluationLimit;
    final double cpuLimit;
    boolean stopped;
    final int[] reference, best, initial;

    Core(long[][] processing, long seed, double cpu, long limit) {
        p = processing; n = p.length; m = p[0].length;
        state = seed; cpuLimit = cpu; evaluationLimit = limit;
        prefix = new long[n + 1][m]; sums = new long[n + 1]; scratch = new long[m];
        reference = new int[n]; randomize(reference);
        referenceCost = cost(reference, n, 0);
        best = reference.clone(); initial = reference.clone(); bestCost = initialCost = referenceCost;
    }
    static double cpu() {
        long value = OS.getProcessCpuTime();
        if (value < 0) throw new IllegalStateException("CPU del proceso no disponible");
        return value / 1000000000.0;
    }
    long next() {
        long z = (state += 0x9E3779B97F4A7C15L);
        z = (z ^ (z >>> 30)) * 0xBF58476D1CE4E5B9L;
        z = (z ^ (z >>> 27)) * 0x94D049BB133111EBL;
        return z ^ (z >>> 31);
    }
    int rand(int bound) {
        long b = bound, threshold = Long.remainderUnsigned(-b, b), value;
        do { value = next(); } while (Long.compareUnsigned(value, threshold) < 0);
        return (int) Long.remainderUnsigned(value, b);
    }
    double uniform() { return (next() >>> 11) * (1.0 / 9007199254740992.0); }
    void randomize(int[] q) {
        for (int i = 0; i < n; ++i) q[i] = i;
        for (int i = n - 1; i > 0; --i) { int j = rand(i + 1), temp = q[i]; q[i] = q[j]; q[j] = temp; }
    }
    boolean active() {
        if (stopped || bestCost == 0) return false;
        if (evaluations >= evaluationLimit || (evaluations % 32 == 0 && cpu() >= cpuLimit)) stopped = true;
        return !stopped;
    }
    void setPrefix(int[] q, int length) {
        for (int i = 0; i < length; ++i) {
            long left = 0;
            for (int j = 0; j < m; ++j) {
                left = Math.max(prefix[i][j], left) + p[q[i]][j];
                prefix[i + 1][j] = left;
            }
            sums[i + 1] = sums[i] + left;
        }
    }
    long cost(int[] q, int length, int start) {
        System.arraycopy(prefix[start], 0, scratch, 0, m);
        long total = sums[start];
        for (int i = start; i < length; ++i) {
            long left = 0;
            for (int j = 0; j < m; ++j) {
                left = Math.max(scratch[j], left) + p[q[i]][j];
                scratch[j] = left;
            }
            total += left;
        }
        return total;
    }
    long evaluate(int[] q, int length, int start) {
        if (!active()) return -1;
        long value = cost(q, length, start);
        ++evaluations;
        if (length == n) {
            checksum += value;
            if (value < bestCost) { bestCost = value; System.arraycopy(q, 0, best, 0, n); }
        }
        return value;
    }
    void setInitial(int[] q, long value) {
        if (value >= 0) { System.arraycopy(q, 0, initial, 0, n); initialCost = value; }
    }
    void insert(int[] q, int[] out, int length, int i, int j) {
        System.arraycopy(q, 0, out, 0, length);
        int job = q[i];
        if (i < j) for (int k = i; k < j; ++k) out[k] = out[k + 1];
        else for (int k = i; k > j; --k) out[k] = out[k - 1];
        out[j] = job;
    }
    long local(int[] q, long value) {
        int[] candidate = new int[n];
        while (active()) {
            setPrefix(q, n);
            boolean improved = false;
            for (int i = 0; i < n && !improved; ++i) for (int j = 0; j < n; ++j) {
                if (i == j) continue;
                insert(q, candidate, n, i, j);
                long c = evaluate(candidate, n, Math.min(i, j));
                if (c < 0) return value;
                if (c < value) { System.arraycopy(candidate, 0, q, 0, n); value = c; improved = true; break; }
            }
            if (improved) continue;
            for (int i = 0; i < n && !improved; ++i) for (int j = i + 1; j < n; ++j) {
                System.arraycopy(q, 0, candidate, 0, n);
                int temp = candidate[i]; candidate[i] = candidate[j]; candidate[j] = temp;
                long c = evaluate(candidate, n, i);
                if (c < 0) return value;
                if (c < value) { System.arraycopy(candidate, 0, q, 0, n); value = c; improved = true; break; }
            }
            if (!improved) break;
        }
        return value;
    }
    long greedy(int[] q, int length, int[] order, int count) {
        int[] candidate = new int[n], chosen = new int[n];
        long value = -1;
        for (int k = 0; k < count; ++k) {
            setPrefix(q, length);
            long minimum = Long.MAX_VALUE;
            for (int pos = 0; pos <= length; ++pos) {
                System.arraycopy(q, 0, candidate, 0, pos);
                candidate[pos] = order[k];
                System.arraycopy(q, pos, candidate, pos + 1, length - pos);
                long c = evaluate(candidate, length + 1, pos);
                if (c < 0) return -1;
                if (c < minimum) { minimum = c; System.arraycopy(candidate, 0, chosen, 0, length + 1); }
            }
            ++length;
            System.arraycopy(chosen, 0, q, 0, length);
            value = minimum;
        }
        return value;
    }
    boolean accept(long old, long value, double temperature) {
        return value <= old || uniform() < Math.exp((old - value) / temperature);
    }
    static String algorithm(String[] args) {
        for (int i = 0; i + 1 < args.length; ++i) if (args[i].equals("--algorithm")) return args[i + 1];
        return "ig";
    }
    static long[][] read(String path) throws Exception {
        Path file = Path.of(path);
        if (Files.size(file) > 1048576) throw new IllegalArgumentException("Archivo demasiado grande");
        String text = Files.readString(file);
        if (text.startsWith("\uFEFF")) text = text.substring(1);
        String[][] lines = text.lines().map(String::strip).filter(s -> !s.isEmpty()).map(s -> s.split("\\s+")).toArray(String[][]::new);
        if (lines.length == 0 || lines[0].length != 2) throw new IllegalArgumentException("Cabecera esperada: n m");
        long jobs = Long.parseLong(lines[0][0]), machines = Long.parseLong(lines[0][1]);
        if (jobs < 1 || machines < 1 || jobs > 10000 || machines > 10000 || jobs * machines > 10000 || lines.length != jobs + 1)
            throw new IllegalArgumentException("Dimensiones o filas incorrectas");
        int n = (int) jobs, m = (int) machines;
        long[][] p = new long[n][m];
        long maximum = 0;
        for (int i = 0; i < n; ++i) {
            if (lines[i + 1].length != 2 * m) throw new IllegalArgumentException("Fila incorrecta");
            for (int j = 0; j < m; ++j) {
                long machine = Long.parseLong(lines[i + 1][2 * j]), duration = Long.parseLong(lines[i + 1][2 * j + 1]);
                if (machine != j || duration < 0) throw new IllegalArgumentException("Par máquina-duración incorrecto");
                p[i][j] = duration; maximum = Math.max(maximum, duration);
            }
        }
        if (maximum > Long.MAX_VALUE / n / (n + m)) throw new IllegalArgumentException("Posible desbordamiento int64");
        return p;
    }
    static String sequence(int[] q, boolean json) {
        StringBuilder result = new StringBuilder(json ? "[" : "");
        for (int i = 0; i < q.length; ++i) { if (i > 0) result.append(json ? ',' : ' '); result.append(q[i] + 1); }
        return result.append(json ? "]" : "").toString();
    }
    static void run(String[] args, Consumer<Core> solve, String selected, boolean contest) {
        try {
            String path = "test.txt";
            long seed = new SecureRandom().nextLong(), limit = Long.MAX_VALUE;
            double cpu = 57;
            boolean hasCpu = false, hasLimit = false;
            for (int i = 0; i < args.length; ++i) {
                String flag = args[i];
                if (flag.equals("--contest")) { contest = true; continue; }
                if (++i == args.length) throw new IllegalArgumentException("Falta el valor del argumento");
                String value = args[i];
                switch (flag) {
                    case "--instance" -> path = value;
                    case "--algorithm" -> { if (!value.equals(selected)) throw new IllegalArgumentException("Algoritmo incorrecto"); }
                    case "--output" -> { if (!value.equals("json")) throw new IllegalArgumentException("Salida incorrecta"); }
                    case "--seed" -> seed = Long.parseUnsignedLong(value);
                    case "--cpu-budget" -> { cpu = Double.parseDouble(value); hasCpu = true; }
                    case "--max-evaluations" -> { limit = Long.parseLong(value); hasLimit = true; }
                    default -> throw new IllegalArgumentException("Argumento desconocido: " + flag);
                }
            }
            if (hasCpu && hasLimit) throw new IllegalArgumentException("Los límites son excluyentes");
            if (hasLimit) cpu = 86400;
            if (!Double.isFinite(cpu) || cpu <= 0 || limit < 1) throw new IllegalArgumentException("Presupuesto incorrecto");
            Core s = new Core(read(path), seed, cpu, limit);
            solve.accept(s);
            if (contest) {
                System.out.printf(Locale.ROOT, "%.10f%n%.6f%n%s%n", (double) s.bestCost / s.n, cpu(), sequence(s.best, false));
            } else {
                System.out.println("{\"algorithm\":\"" + selected + "\",\"seed\":" + Long.toUnsignedString(seed)
                    + ",\"reference_cost\":" + s.referenceCost + ",\"initial_cost\":" + s.initialCost + ",\"cost\":" + s.bestCost
                    + ",\"fmed_reference\":" + (double) s.referenceCost / s.n + ",\"fmed_initial\":" + (double) s.initialCost / s.n
                    + ",\"fmed_final\":" + (double) s.bestCost / s.n + ",\"reference_sequence\":" + sequence(s.reference, true)
                    + ",\"initial_sequence\":" + sequence(s.initial, true) + ",\"sequence\":" + sequence(s.best, true)
                    + ",\"evaluations\":" + s.evaluations + ",\"cost_checksum\":" + Long.toUnsignedString(s.checksum) + ",\"cpu_seconds\":" + cpu() + "}");
            }
        } catch (Exception error) { System.err.println(error.getMessage()); System.exit(1); }
    }
}
