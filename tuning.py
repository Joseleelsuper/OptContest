import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import zipfile

import bench

ROOT = bench.ROOT
BUILD = ROOT / "build/tuning"
BASE = "cpp-ig-base"
DELIVERY = "cpp-ig-r400"
VARIANTS = {
    BASE: (6, 100, 200),
    "cpp-ig-d4": (4, 100, 200),
    "cpp-ig-d8": (8, 100, 200),
    "cpp-ig-t50": (6, 50, 200),
    "cpp-ig-t200": (6, 200, 200),
    "cpp-ig-r100": (6, 100, 100),
    "cpp-ig-r400": (6, 100, 400),
}
FLAGS = ["-std=c++20", "-O3", "-DNDEBUG", "-static-libgcc", "-static-libstdc++"]


def source_hash():
    return hashlib.sha256(bench.fingerprint().encode() + Path(__file__).read_bytes()).hexdigest()


def build():
    BUILD.mkdir(parents=True, exist_ok=True)
    commands, hashes = [], {}
    for name, parameters in VARIANTS.items():
        source, binary = BUILD / f"{name}.cpp", BUILD / f"{name}.exe"
        solve = f"ig_search<{','.join(map(str, parameters))}>"
        source.write_text(f'#include "ig.hpp"\nint main(int argc, char** argv) {{ return run(argc, argv, {solve}, "ig"); }}\n', encoding="utf-8")
        command = ["g++", *FLAGS, "-I", ROOT / "solvers/cpp", source, "-o", binary]
        bench.call(command)
        commands.append(list(map(str, command)))
        hashes[name] = hashlib.sha256(binary.read_bytes()).hexdigest()
    metadata = {"source_hash": source_hash(), "variants": VARIANTS, "commands": commands, "binary_hashes": hashes,
                "compiler": bench.call(["g++", "--version"], capture_output=True).stdout.strip()}
    (BUILD / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def configure():
    path = BUILD / "metadata.json"
    metadata = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if metadata.get("source_hash") != source_hash() or not all((BUILD / f"{name}.exe").exists() for name in VARIANTS):
        metadata = build()

    def command(name):
        binary = BUILD / f"{name}.exe"
        if source_hash() != metadata["source_hash"] or hashlib.sha256(binary.read_bytes()).hexdigest() != metadata["binary_hashes"][name]:
            raise RuntimeError("Cambió el código o el ejecutable durante el ajuste")
        return [str(binary)]

    bench.command = command
    bench.runtime_versions = lambda: {"controller_python": sys.version, "tuning": metadata}
    bench.build = lambda: {"source_hash": bench.fingerprint()} | bench.runtime_versions()


def campaign(folder, names, inputs, count, repetitions):
    bench.generate_instances = lambda amount: [ROOT / "instances" / inputs / f"{i + 1:02}.txt" for i in range(amount)]
    bench.run(argparse.Namespace(instances=count, repetitions=repetitions, cpu_budget=57,
                                languages=names, algorithms=["ig"], phase="cpu", results=folder))
    rows = bench.records(folder)
    if len(rows) != count * repetitions * len(names) or any(row["status"] == "interrupted" for row in rows):
        raise RuntimeError("Campaña incompleta; repite el mismo comando para reanudar")
    return rows


def choose(rows):
    groups = {name: [row for row in rows if row["language"] == name] for name in VARIANTS}
    if not groups[BASE] or any(row["status"] != "ok" for row in groups[BASE]):
        raise RuntimeError("La referencia tiene fallos; no se puede seleccionar una mejora")
    eligible = [name for name, samples in groups.items()
                if len(samples) == len(groups[BASE]) and all(row["status"] == "ok" for row in samples)]
    return min(eligible, key=lambda name: (statistics.mean(row["fmed_final"] for row in groups[name]), name != BASE, name))


def paired(rows, candidate):
    pairs = {}
    for row in rows:
        pairs.setdefault((row["instance"], row["seed"]), {})[row["language"]] = row["fmed_final"]
    differences, instances = [], {}
    for (instance, _), pair in pairs.items():
        delta = pair[candidate] - pair[BASE]
        differences.append(delta)
        instances.setdefault(instance, []).append(delta)
    means = [statistics.mean(values) for values in instances.values()]
    rng = random.Random(0)
    bootstrap = sorted(statistics.mean(rng.choices(means, k=len(means))) for _ in range(10000))
    return {"candidate_minus_base": statistics.mean(differences),
            "wins": sum(delta < 0 for delta in differences), "ties": differences.count(0),
            "losses": sum(delta > 0 for delta in differences),
            "by_instance": {name: statistics.mean(values) for name, values in instances.items()},
            "bootstrap_95_by_instance": [bootstrap[249], bootstrap[9749]]}


def run(folder):
    folder = Path(folder).resolve()
    training = campaign(folder / "search", list(VARIANTS), "tuning", 5, 2)
    candidate = choose(training)
    decision = {"candidate": candidate, "parameters": VARIANTS[candidate], "selected": BASE,
                "stage": "validation" if candidate != BASE else "complete"}
    path = folder / "selection.json"
    path.write_text(json.dumps(decision, indent=2), encoding="utf-8")
    if candidate != BASE:
        validation = campaign(folder / "validation", [BASE, candidate], "tuning-validation", 10, 5)
        if any(row["status"] != "ok" for row in validation):
            decision.update(stage="validation_failed", selected=None)
        else:
            comparison = paired(validation, candidate)
            decision.update(stage="complete", comparison=comparison)
            if comparison["bootstrap_95_by_instance"][1] < 0:
                decision["selected"] = candidate
        path.write_text(json.dumps(decision, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(decision, indent=2), flush=True)


def export(team, destination=None):
    folder = bench.export("cpp", "ig", team, destination)
    entry = next(folder.glob("optcontest*.cpp"))
    name = entry.stem
    destruction, temperature, restart = VARIANTS[DELIVERY]
    solve = f"ig_search<{destruction},{temperature},{restart}>"
    entry.write_text(f'#include "ig.hpp"\nint main(int argc, char** argv) {{ return run(argc, argv, {solve}, "ig", true); }}\n', encoding="utf-8")
    flags = [*FLAGS, "-static"]
    bench.call(["g++", *flags, entry, "-o", folder / f"{name}.exe"])
    (folder / "leeme.txt").write_text(
        f"OptContest - equipo {name.removeprefix('optcontest')}\nWindows 11 x64. C++/IG, un hilo.\n\n"
        f"1. Extrae el ZIP en una carpeta.\n2. Coloca test.txt en esa carpeta.\n"
        f"3. Abre PowerShell en esa carpeta y ejecuta:\n\n.\\{name}.exe\n\n"
        "Salida, en tres lineas: Fmed, segundos de CPU y secuencia de ordenes desde 1.\n"
        "Presupuesto: 57 segundos de CPU, incluidos arranque e inicializacion.\n"
        f"Parametros: destruccion de hasta {destruction} ordenes, temperatura max(1, {temperature / 10000:g} * coste inicial), "
        f"reinicio tras {restart} ciclos sin mejora global.\n"
        "Cada ejecucion sin semilla explicita utiliza una semilla nueva.\n"
        "El ejecutable no necesita Python, Java ni compilador instalado.\n\n"
        f"Compilacion opcional con GCC/MinGW y C++20:\ng++ {' '.join(flags)} {name}.cpp -o {name}.exe\n\n"
        f"Comprobacion reproducible por evaluaciones:\n.\\{name}.exe --seed 42 --max-evaluations 2000000\n",
        encoding="utf-8")
    archive = folder.parent / f"{name}.zip"
    with archive.open("xb") as output, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(folder.iterdir()): bundle.write(path, path.name)
    archive.with_suffix(".zip.sha256").write_text(f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n", encoding="ascii")
    return archive


def export_check():
    with tempfile.TemporaryDirectory(prefix="optcontest-delivery-") as directory:
        root = Path(directory).resolve()
        archive = export("A2", root / "source")
        with zipfile.ZipFile(archive) as bundle:
            assert set(bundle.namelist()) == {"optcontestA2.cpp", "optcontestA2.exe", "core.hpp", "ig.hpp", "leeme.txt", "LICENSE"}
            bundle.extractall(root / "run")
        instance = ROOT / "instances/examples/Doc11.txt"
        shutil.copyfile(instance, root / "run/test.txt")
        env = os.environ | {"PATH": str(Path(os.environ["SystemRoot"]) / "System32")}
        result = subprocess.run([str(root / "run/optcontestA2.exe"), "--seed", "42", "--max-evaluations", "2000000"],
                                cwd=root / "run", env=env, check=True, capture_output=True, text=True, timeout=60)
        lines = result.stdout.strip().splitlines()
        assert len(lines) == 3 and not result.stderr
        sequence = list(map(int, lines[2].split()))
        assert sorted(sequence) == list(range(1, 76)) and float(lines[1]) >= 0
        assert abs(float(lines[0]) - bench.flowtime(bench.read_instance(instance), sequence) / 75) < 1e-9
        reference = json.loads(bench.call([BUILD / f"{DELIVERY}.exe", "--instance", instance, "--seed", "42",
                                          "--max-evaluations", "2000000"], capture_output=True).stdout)
        assert sequence == reference["sequence"] and abs(float(lines[0]) - reference["fmed_final"]) < 1e-9
        numeric = bench.export("cpp", "ig", "1", root / "numeric")
        assert (numeric / "optcontest01.cpp").exists()
        for team in ("", "../A2", "A-2", "A 2", "Á2", "A234567"):
            try: bench.export("cpp", "ig", team, root / "invalid")
            except ValueError: pass
            else: raise AssertionError(team)
    print("ZIP A2, nombres, dependencias y equivalencia con r400: correctos", flush=True)


def checks():
    keys = ("reference_cost", "initial_cost", "cost", "reference_sequence", "initial_sequence", "sequence", "evaluations", "cost_checksum")
    instance = ROOT / "instances/examples/Doc11.txt"
    reference = bench.execute("cpp", "ig", instance, 42, evaluations=2000000)
    assert reference["status"] == "ok", reference
    configure()
    signatures = set()
    for name in VARIANTS:
        a = bench.execute(name, "ig", instance, 42, evaluations=2000000)
        b = bench.execute(name, "ig", instance, 42, evaluations=2000000)
        assert a["status"] == b["status"] == "ok" and a["evaluations"] == 2000000, (a, b)
        assert all(a[key] == b[key] for key in keys), name
        if name == BASE: assert all(a[key] == reference[key] for key in keys), (a, reference)
        signatures.add((a["cost"], a["cost_checksum"]))
    assert len(signatures) > 1
    for name in (BASE, "cpp-ig-d8"):
        row = bench.execute(name, "ig", instance, 42, cpu=0.5)
        assert row["status"] == "ok" and row["cpu_seconds"] <= 1, row
    samples = [{"language": BASE, "status": "ok", "fmed_final": 2},
               {"language": "cpp-ig-d4", "status": "ok", "fmed_final": 1}]
    assert choose(samples) == "cpp-ig-d4"
    samples[1]["status"] = "crash"
    assert choose(samples) == BASE
    samples[1].update(status="ok", fmed_final=2)
    assert choose(samples) == BASE
    rows = [dict(instance=str(i), seed=1, language=name, fmed_final=value)
            for i in range(2) for name, value in ((BASE, 2), ("cpp-ig-d4", 1))]
    comparison = paired(rows, "cpp-ig-d4")
    assert comparison["wins"] == 2 and comparison["bootstrap_95_by_instance"] == [-1, -1]
    export_check()
    print("Siete variantes reproducibles; base idéntica, costes, presupuesto, selección y comparación: correctos", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Ajuste y validación separados, solo C++/IG secuencial")
    parser.add_argument("action", choices=("check", "run", "export"))
    parser.add_argument("--results", type=Path, default=ROOT / "results/ig-tuning")
    parser.add_argument("--team")
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    if args.action == "export":
        if args.team is None: parser.error("export requiere --team")
        print(export(args.team, args.destination))
    elif args.action == "check": checks()
    else: configure(); run(args.results)


if __name__ == "__main__":
    main()
