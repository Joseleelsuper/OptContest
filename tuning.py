import argparse
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys

import bench

ROOT = bench.ROOT
BUILD = ROOT / "build/tuning"
BASE = "cpp-ig-base"
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
    print("Siete variantes reproducibles; base idéntica, costes, presupuesto, selección y comparación: correctos", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Ajuste y validación separados, solo C++/IG secuencial")
    parser.add_argument("action", choices=("check", "run"))
    parser.add_argument("--results", type=Path, default=ROOT / "results/ig-tuning")
    args = parser.parse_args()
    if args.action == "check": checks()
    else: configure(); run(args.results)


if __name__ == "__main__":
    main()
