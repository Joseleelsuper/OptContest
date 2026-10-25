import itertools
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np

import bench

sys.path.insert(0, str(bench.ROOT / "solvers/python"))
from core import Search


def kernel_checks():
    p = np.array(bench.read_instance(bench.ROOT / "instances/examples/class1.txt"), dtype=np.int64)
    s = Search(p, np.uint64(0), 300.0, 100000)
    s.state = np.uint64(0)
    assert [int(s.next()) for _ in range(3)] == [0xE220A8397B1DCDAF, 0x6E789E6AA1B965F4, 0x06C45D188009454F]
    candidate = np.empty(s.n, dtype=np.int64)
    optimum = 2**63 - 1
    for permutation in itertools.permutations(range(s.n)):
        q = np.array(permutation, dtype=np.int64)
        s.set_prefix(q, s.n)
        value = bench.flowtime(p.tolist(), (q + 1).tolist())
        optimum = min(optimum, value)
        assert s.cost(q, s.n, 0) == value
        for i in range(s.n):
            assert s.cost(q, s.n, i) == value
            for j in range(s.n):
                s.insert(q, candidate, s.n, i, j)
                expected = bench.flowtime(p.tolist(), (candidate + 1).tolist())
                assert s.cost(candidate, s.n, min(i, j)) == expected
                candidate[:] = q
                candidate[i], candidate[j] = candidate[j], candidate[i]
                assert s.cost(candidate, s.n, min(i, j)) == bench.flowtime(p.tolist(), (candidate + 1).tolist())
    assert optimum == 76
    assert min(bench.flowtime([[1, 10], [3, 1]], q) for q in itertools.permutations((1, 2))) == 18
    assert bench.flowtime([[0]], [1]) == 0


def solver_checks():
    keys = ("reference_cost", "initial_cost", "cost", "reference_sequence", "initial_sequence", "sequence", "evaluations", "cost_checksum")
    for filename in ("class1.txt", "Doc11.txt"):
        for algorithm in bench.ALGORITHMS:
            expected = None
            for language in bench.LANGUAGES:
                row = bench.execute(language, algorithm, bench.ROOT / "instances/examples" / filename, 42, evaluations=4096)
                assert row["status"] == "ok", row
                signature = {key: row[key] for key in keys}
                if expected is None: expected = signature
                assert signature == expected, (filename, algorithm, language, signature, expected)
                assert row["evaluations"] == 4096
            print(f"Equivalencia: {filename}/{algorithm}", flush=True)
    expected = None
    for language in bench.LANGUAGES:
        row = bench.execute(language, "random", bench.ROOT / "instances/examples/class2.txt", 2**64 - 1, evaluations=10000)
        assert row["status"] == "ok", row
        signature = {key: row[key] for key in keys}
        if expected is None: expected = signature
        assert signature == expected


def boundary_checks(folder):
    path = folder / "test.txt"
    cases = ["", "1 1\n0 -1\n", "1 1\n1 2\n", "2 1\n0 1\n", "1 1\n0 1 0 2\n", "1 1\n0 9223372036854775807\n"]
    for text in cases:
        path.write_text(text, encoding="utf-8")
        for language in bench.LANGUAGES:
            result = subprocess.run(bench.command(language) + ["--instance", str(path), "--max-evaluations", "1"], capture_output=True, timeout=30)
            assert result.returncode != 0 and not result.stdout, (text, language, result.stdout)
    for text, expected in (("\ufeff\r\n1 1\r\n0 7\r\n\r\n", 7), ("1 1\n0 0\n", 0)):
        path.write_text(text, encoding="utf-8")
        for language in bench.LANGUAGES:
            row = bench.execute(language, "ig", path, 0, evaluations=10)
            assert row["status"] == "ok" and row["cost"] == expected, row
    for language in bench.LANGUAGES:
        budget = 10.0 if language == "numba" else 0.5
        for algorithm in bench.ALGORITHMS if language == "numba" else ("ig",):
            row = bench.execute(language, algorithm, bench.ROOT / "instances/examples/Doc11.txt", 42, cpu=budget)
            assert row["status"] == "ok", row
            assert row["cpu_seconds"] <= budget + (0 if language == "numba" else 0.5), row
            print(f"CPU: {language}/{algorithm} {row['cpu_seconds']:.3f}s", flush=True)
    original = bench.command
    try:
        for script, status in (("print('broken')", "invalid_output"), ("print('NaN')", "invalid_output"), ("print('{}')", "invalid_solution"),
                               ("raise SystemExit(7)", "crash"), ("while True: pass", "timeout")):
            bench.command = lambda language, script=script: [str(bench.PYTHON), "-c", script]
            row = bench.execute("python", "random", bench.ROOT / "instances/examples/class1.txt", 42, cpu=0.01)
            assert row["status"] == status, row
    finally:
        bench.command = original


def export_checks(folder):
    p = bench.read_instance(bench.ROOT / "instances/examples/class1.txt")
    for language in bench.LANGUAGES:
        for algorithm in bench.ALGORITHMS:
            exported = bench.export(language, algorithm, "99", folder / f"{language}-{algorithm}")
            (exported / "test.txt").write_bytes((bench.ROOT / "instances/examples/class1.txt").read_bytes())
            if language == "cpp":
                build = ["g++", "-std=c++20", "-O3", "-static-libgcc", "-static-libstdc++", "optcontest99.cpp", "-o", "optcontest99.exe"]
                command = [str(exported / "optcontest99.exe")]
            elif language == "rust":
                build = [str(bench.RUSTC) if bench.RUSTC.exists() else "rustc", "--edition=2024", "-O", "-A", "dead_code", "optcontest99.rs", "-o", "optcontest99.exe"]
                command = [str(exported / "optcontest99.exe")]
            elif language == "java":
                build = ["javac", "--release", "17", "-encoding", "UTF-8", *[p.name for p in exported.glob("*.java")]]
                command = ["java", "-cp", str(exported), "optcontest99"]
            else:
                build = None
                command = [str(bench.PYTHON), str(exported / "optcontest99.py")]
            if build:
                subprocess.run(build, cwd=exported, env=bench.rust_env(), check=True, capture_output=True, timeout=60)
            result = subprocess.run(command + ["--seed", "42", "--max-evaluations", "1000"], cwd=exported, capture_output=True, text=True, encoding="utf-8", timeout=60)
            assert result.returncode == 0, (language, algorithm, result.stderr)
            lines = result.stdout.strip().splitlines()
            assert len(lines) == 3, (language, algorithm, result.stdout)
            sequence = list(map(int, lines[2].split()))
            assert sorted(sequence) == list(range(1, 6)) and float(lines[0]) == bench.flowtime(p, sequence) / 5
            assert float(lines[1]) >= 0
        print(f"Entrega independiente: {language}", flush=True)


def controller_checks(folder):
    args = [str(bench.PYTHON), str(bench.ROOT / "bench.py"), "run", "--instances", "1", "--repetitions", "1",
            "--cpu-budget", "0.1", "--languages", "cpp", "--algorithms", "ig", "--results", str(folder)]
    subprocess.run(args, check=True, capture_output=True, timeout=60)
    path = folder / "runs.jsonl"
    original = path.read_bytes()
    assert len(bench.records(folder)) == 2
    with path.open("ab") as file: file.write(b'{"incomplete":"\xc3')
    subprocess.run(args, check=True, capture_output=True, timeout=60)
    assert path.read_bytes() == original
    assert all(row["status"] == "ok" for row in bench.records(folder))
    assert (folder / "runs.csv").is_file() and (folder / "report.html").is_file()
    assert "COMPLETO" in (folder / "report.html").read_text(encoding="utf-8")
    print("Controlador: medición, informes y reanudación correctos", flush=True)


if __name__ == "__main__":
    kernel_checks()
    print("Evaluador completo, incremental y óptimos pequeños: correctos", flush=True)
    if "--kernel-only" not in sys.argv:
        solver_checks()
        subprocess.run([str(bench.PYTHON), __file__, "--numba", "--kernel-only"], check=True, timeout=60)
        with tempfile.TemporaryDirectory(prefix="optcontest-check-") as directory:
            folder = Path(directory)
            boundary_checks(folder)
            export_checks(folder)
            controller_checks(folder / "campaign")
        print("Todas las comprobaciones superadas", flush=True)
