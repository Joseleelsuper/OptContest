import ctypes
import math
import sys

import numpy as np

np.seterr(over="ignore")
NUMBA = "--numba" in sys.argv
get_times = ctypes.WINFUNCTYPE(ctypes.c_int, *([ctypes.c_int64] * 5))(
    ("GetProcessTimes", ctypes.WinDLL("kernel32"))
)


class Search:
    def __init__(self, processing, seed, cpu_limit, evaluation_limit):
        self.p = processing
        self.n, self.m = processing.shape
        self.state = np.uint64(seed)
        self.cpu_limit = cpu_limit
        self.evaluation_limit = evaluation_limit
        self.evaluations = 0
        self.checksum = np.uint64(0)
        self.stopped = False
        self.clock = np.zeros(4, dtype=np.int64)
        self.prefix = np.zeros((self.n + 1, self.m), dtype=np.int64)
        self.sums = np.zeros(self.n + 1, dtype=np.int64)
        self.scratch = np.zeros(self.m, dtype=np.int64)
        self.reference = np.arange(self.n, dtype=np.int64)
        self.randomize(self.reference)
        self.reference_cost = self.cost(self.reference, self.n, 0)
        self.best = self.reference.copy()
        self.best_cost = self.reference_cost
        self.initial = self.reference.copy()
        self.initial_cost = self.reference_cost

    def next(self):
        self.state = self.state + np.uint64(0x9E3779B97F4A7C15)
        z = self.state
        z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        return z ^ (z >> np.uint64(31))

    def rand(self, bound):
        b = np.uint64(bound)
        threshold = (np.uint64(0) - b) % b
        value = self.next()
        while value < threshold:
            value = self.next()
        return np.int64(value % b)

    def uniform(self):
        return float(self.next() >> np.uint64(11)) * (1.0 / 9007199254740992.0)

    def randomize(self, q):
        for i in range(self.n):
            q[i] = i
        for i in range(self.n - 1, 0, -1):
            j = self.rand(i + 1)
            q[i], q[j] = q[j], q[i]

    def cpu(self):
        address = self.clock.ctypes.data
        if not get_times(-1, address, address + 8, address + 16, address + 24):
            raise RuntimeError("GetProcessTimes failed")
        return (self.clock[2] + self.clock[3]) / 10000000.0

    def active(self):
        if self.stopped or self.best_cost == 0:
            return False
        if self.evaluations >= self.evaluation_limit:
            self.stopped = True
        elif self.evaluations % 32 == 0 and self.cpu() >= self.cpu_limit:
            self.stopped = True
        return not self.stopped

    def set_prefix(self, q, length):
        for i in range(length):
            left = 0
            for j in range(self.m):
                left = max(self.prefix[i, j], left) + self.p[q[i], j]
                self.prefix[i + 1, j] = left
            self.sums[i + 1] = self.sums[i] + left

    def cost(self, q, length, start):
        for j in range(self.m):
            self.scratch[j] = self.prefix[start, j]
        total = self.sums[start]
        for i in range(start, length):
            left = 0
            for j in range(self.m):
                left = max(self.scratch[j], left) + self.p[q[i], j]
                self.scratch[j] = left
            total += left
        return total

    def evaluate(self, q, length, start):
        if not self.active():
            return -1
        value = self.cost(q, length, start)
        self.evaluations += 1
        if length == self.n:
            self.checksum = self.checksum + np.uint64(value)
            if value < self.best_cost:
                self.best_cost = value
                self.best[:] = q
        return value

    def set_initial(self, q, value):
        if value >= 0:
            self.initial[:] = q
            self.initial_cost = value

    def positions(self):
        i = self.rand(self.n)
        j = self.rand(self.n - 1)
        if j >= i:
            j += 1
        return i, j

    def insert(self, q, out, length, i, j):
        out[:length] = q[:length]
        job = q[i]
        if i < j:
            for k in range(i, j):
                out[k] = out[k + 1]
        else:
            for k in range(i, j, -1):
                out[k] = out[k - 1]
        out[j] = job

    def local(self, q, value):
        candidate = np.empty(self.n, dtype=np.int64)
        while self.active():
            self.set_prefix(q, self.n)
            improved = False
            for i in range(self.n):
                for j in range(self.n):
                    if i == j:
                        continue
                    self.insert(q, candidate, self.n, i, j)
                    cost = self.evaluate(candidate, self.n, min(i, j))
                    if cost < 0:
                        return value
                    if cost < value:
                        q[:] = candidate
                        value, improved = cost, True
                        break
                if improved:
                    break
            if improved:
                continue
            for i in range(self.n):
                for j in range(i + 1, self.n):
                    candidate[:] = q
                    candidate[i], candidate[j] = candidate[j], candidate[i]
                    cost = self.evaluate(candidate, self.n, i)
                    if cost < 0:
                        return value
                    if cost < value:
                        q[:] = candidate
                        value, improved = cost, True
                        break
                if improved:
                    break
            if not improved:
                break
        return value

    def greedy(self, q, length, order, count):
        candidate = np.empty(self.n, dtype=np.int64)
        chosen = np.empty(self.n, dtype=np.int64)
        value = -1
        for k in range(count):
            self.set_prefix(q, length)
            minimum = np.int64(9223372036854775807)
            for pos in range(length + 1):
                for i in range(pos):
                    candidate[i] = q[i]
                candidate[pos] = order[k]
                for i in range(pos, length):
                    candidate[i + 1] = q[i]
                cost = self.evaluate(candidate, length + 1, pos)
                if cost < 0:
                    return -1
                if cost < minimum:
                    minimum = cost
                    chosen[:length + 1] = candidate[:length + 1]
            length += 1
            q[:length] = chosen[:length]
            value = minimum
        return value

    def accept(self, old, new, temperature):
        return new <= old or self.uniform() < math.exp((old - new) / temperature)


if NUMBA:
    from numba import boolean, float64, int64, uint64
    from numba.experimental import jitclass

    Search = jitclass([
        ("p", int64[:, ::1]), ("n", int64), ("m", int64), ("state", uint64),
        ("cpu_limit", float64), ("evaluation_limit", int64), ("evaluations", int64),
        ("checksum", uint64), ("stopped", boolean), ("clock", int64[::1]),
        ("prefix", int64[:, ::1]), ("sums", int64[::1]), ("scratch", int64[::1]),
        ("reference", int64[::1]), ("reference_cost", int64), ("best", int64[::1]),
        ("best_cost", int64), ("initial", int64[::1]), ("initial_cost", int64),
    ])(Search)
