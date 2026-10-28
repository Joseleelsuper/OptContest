import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import bench

ROOT = bench.ROOT
BINARY = ROOT / "build/ig-parallel.exe"
FLAGS = ["-std=c++20", "-O3", "-DNDEBUG", "-march=x86-64-v3", "-static", "-pthread"]
original_command = bench.command
original_instances = bench.generate_instances


def source_hash():
    digest = hashlib.sha256(bench.fingerprint().encode())
    for path in (ROOT / "hardware.py", ROOT / "experiments/parallel.hpp", ROOT / "experiments/parallel.cpp"):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def build():
    BINARY.parent.mkdir(parents=True, exist_ok=True)
    commands = [
        ["g++", "-std=c++20", "-O3", "-DNDEBUG", "-static-libgcc", "-static-libstdc++", ROOT / "solvers/cpp/main.cpp", "-o", ROOT / "build/cpp.exe"],
        ["g++", *FLAGS, "-I", ROOT / "solvers/cpp", ROOT / "experiments/parallel.cpp", "-o", BINARY],
    ]
    for command in commands: bench.call(command)
    metadata = {"source_hash": source_hash(), "commands": [list(map(str, command)) for command in commands],
                "compiler": bench.call(["g++", "--version"], capture_output=True).stdout.strip(),
                "reference_hash": hashlib.sha256((ROOT / "build/cpp.exe").read_bytes()).hexdigest(),
                "binary_hash": hashlib.sha256(BINARY.read_bytes()).hexdigest()}
    (ROOT / "build/hardware.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def configure():
    path = ROOT / "build/hardware.json"
    metadata = json.loads(path.read_text()) if path.exists() and BINARY.exists() and (ROOT / "build/cpp.exe").exists() else {}
    if metadata.get("source_hash") != source_hash(): metadata = build()

    def command(language):
        if source_hash() != metadata["source_hash"] or hashlib.sha256(BINARY.read_bytes()).hexdigest() != metadata["binary_hash"]:
            raise RuntimeError("Cambió la variante experimental durante la campaña")
        if language == "cpp-ref":
            if hashlib.sha256((ROOT / "build/cpp.exe").read_bytes()).hexdigest() != metadata["reference_hash"]:
                raise RuntimeError("Cambió la referencia durante la campaña")
            return original_command("cpp")
        return [str(BINARY), "--threads", language.removeprefix("cpp-v3-t")]

    bench.command = command
    bench.runtime_versions = lambda: {"controller_python": sys.version, "hardware": metadata}
    bench.build = lambda: {"cpp": metadata["compiler"], "commands": metadata["commands"],
                          "source_hash": bench.fingerprint()} | bench.runtime_versions()


def checks():
    keys = ("reference_cost", "initial_cost", "cost", "reference_sequence", "initial_sequence", "sequence", "evaluations", "cost_checksum")
    instance = ROOT / "instances/examples/Doc11.txt"
    reference = bench.execute("cpp-ref", "ig", instance, 42, evaluations=4097)
    assert reference["status"] == "ok", reference
    for threads in (1, 2, 0):
        name = f"cpp-v3-t{threads}"
        a = bench.execute(name, "ig", instance, 42, evaluations=4097)
        b = bench.execute(name, "ig", instance, 42, evaluations=4097)
        assert a["status"] == b["status"] == "ok", (a, b)
        assert a["evaluations"] == 4097 and all(a[key] == b[key] for key in keys), (a, b)
        if threads == 1: assert all(a[key] == reference[key] for key in keys), (a, reference)
    for limit in (1, 7):
        row = bench.execute("cpp-v3-t0", "ig", instance, 42, evaluations=limit)
        assert row["status"] == "ok" and row["evaluations"] == limit, row
    row = bench.execute("cpp-v3-t0", "ig", instance, 42, cpu=10)
    assert row["status"] == "ok" and row["cpu_seconds"] <= 10.5, row
    print(f"Todos los hilos: CPU total={row['cpu_seconds']:.3f}s, reloj={row['wall_seconds']:.3f}s", flush=True)
    for args in (("--threads",), ("--threads", "-1"), ("--threads", "257"), ("--threads", "2x")):
        result = subprocess.run([str(BINARY), *args], capture_output=True, timeout=10)
        assert result.returncode and not result.stdout, result
    with tempfile.TemporaryDirectory(prefix="optcontest-hardware-") as directory:
        folder = export("99", 0, Path(directory) / "candidate")
        shutil.copyfile(instance, folder / "test.txt")
        subprocess.run(["g++", *FLAGS, "optcontest99.cpp", "-o", "optcontest99.exe"], cwd=folder, check=True, capture_output=True)
        result = subprocess.run([str(folder / "optcontest99.exe"), "--seed", "42", "--max-evaluations", "4097"], cwd=folder, check=True, capture_output=True, text=True)
        lines = result.stdout.strip().splitlines()
        assert len(lines) == 3
        sequence = list(map(int, lines[2].split()))
        assert sorted(sequence) == list(range(1, 76))
        assert abs(float(lines[0]) - bench.flowtime(bench.read_instance(instance), sequence) / 75) < 1e-9
    print("Reparto de evaluaciones, reproducibilidad, presupuesto compartido y entrega: correctos", flush=True)


def export(team, threads, destination=None):
    folder = bench.export("cpp", "ig", team, destination)
    shutil.copyfile(ROOT / "experiments/parallel.hpp", folder / "parallel.hpp")
    name = f"optcontest{int(team):02}"
    (folder / f"{name}.cpp").write_text(f'#include "parallel.hpp"\nint main(int argc, char** argv) {{ worker_count = {threads}; return parallel_run(argc, argv, true); }}\n', encoding="utf-8")
    (folder / "leeme.txt").write_text(f"Windows 11 x64 con AVX2. C++/IG, {threads or 'todos los'} hilos.\n"
        f"g++ {' '.join(FLAGS)} {name}.cpp -o {name}.exe\n.\\{name}.exe\n"
        "Lee test.txt. Salida: Fmed, CPU y secuencia. Presupuesto: 57 s de CPU total entre todos los hilos.\n"
        "--threads 0 usa todos los procesadores lógicos; --threads 1 ejecuta IG secuencial.\n", encoding="utf-8")
    return folder


def main():
    parser = argparse.ArgumentParser(description="C++/IG: AVX2 y búsquedas paralelas con CPU total compartida")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("build"); commands.add_parser("check")
    run = commands.add_parser("run")
    run.add_argument("--instances", type=int, choices=range(1, 11), default=5)
    run.add_argument("--instance-dir", type=Path)
    run.add_argument("--repetitions", type=int, choices=range(1, 6), default=2)
    run.add_argument("--threads", nargs="+", type=int, default=[1, 2, 4, 8, 0])
    run.add_argument("--results", default=str(ROOT / "results/hardware"))
    delivery = commands.add_parser("export")
    delivery.add_argument("--team", required=True)
    delivery.add_argument("--threads", type=int, default=0)
    delivery.add_argument("--destination", type=Path)
    args = parser.parse_args()
    threads = getattr(args, "threads", 0)
    if any(not 0 <= n <= 256 for n in (threads if isinstance(threads, list) else [threads])):
        parser.error("Hilos entre 0 y 256; 0 usa todos")
    if args.action == "build": build(); return
    if args.action == "export": print(export(args.team, args.threads, args.destination)); return
    configure()
    if args.action == "check": checks()
    else:
        if args.instance_dir is None: original_instances(10)
        folder = ROOT / (args.instance_dir or "instances/tuning")
        bench.generate_instances = lambda count: [folder / f"{i + 1:02}.txt" for i in range(count)]
        args.languages = ["cpp-ref"] + [f"cpp-v3-t{n}" for n in dict.fromkeys(args.threads)]
        args.algorithms, args.phase, args.cpu_budget = ["ig"], "cpu", 57
        bench.run(args)


if __name__ == "__main__":
    main()
