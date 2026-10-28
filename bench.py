import argparse
import csv
import hashlib
import html
import itertools
import json
import math
import msvcrt
import os
from pathlib import Path
import platform
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request

import winjob

ROOT = Path(__file__).resolve().parent
LANGUAGES = ("cpp", "rust", "java", "python", "numba")
ALGORITHMS = ("random", "local", "sa", "ga", "ig")
MODULES = {"random": "random_search", "local": "local_search", "sa": "sa", "ga": "ga", "ig": "ig"}
JAVA_CLASSES = {"random": "RandomSearch", "local": "LocalSearch", "sa": "Sa", "ga": "Ga", "ig": "Ig"}
RESULT_FIELDS = {"algorithm", "seed", "reference_cost", "initial_cost", "cost", "fmed_reference", "fmed_initial", "fmed_final",
                 "reference_sequence", "initial_sequence", "sequence", "evaluations", "cost_checksum", "cpu_seconds"}
PYTHON = ROOT / ".venv/Scripts/python.exe"
RUSTC = ROOT / ".tools/cargo/bin/rustc.exe"


def rust_env():
    return os.environ | {"RUSTUP_HOME": str(ROOT / ".tools/rustup"), "CARGO_HOME": str(ROOT / ".tools/cargo")}


def call(command, **kwargs):
    return subprocess.run(list(map(str, command)), cwd=ROOT, check=True, text=True, encoding="utf-8", **kwargs)


def setup():
    if not PYTHON.exists():
        if shutil.which("uv"):
            call(["uv", "venv", "--python", "3.14.5", ROOT / ".venv"])
        else:
            call([sys.executable, "-m", "venv", ROOT / ".venv"])
    if shutil.which("uv"):
        call(["uv", "pip", "install", "--python", PYTHON, "-r", ROOT / "requirements.txt"])
    else:
        call([PYTHON, "-m", "pip", "install", "-r", ROOT / "requirements.txt"])
    if not RUSTC.exists() and not shutil.which("rustc"):
        installer = ROOT / ".tools/rustup-init.exe"
        installer.parent.mkdir(exist_ok=True)
        urllib.request.urlretrieve("https://win.rustup.rs/x86_64", installer)
        call([installer, "-y", "--no-modify-path", "--profile", "minimal", "--default-host",
              "x86_64-pc-windows-gnu", "--default-toolchain", "1.99.1"], env=rust_env())
    for name in ("g++", "javac", "java"):
        if not shutil.which(name):
            raise RuntimeError(f"Falta {name}; instala GCC/MinGW o un JDK 17+ y añádelo al PATH")


def fingerprint():
    digest = hashlib.sha256()
    paths = [ROOT / "bench.py", ROOT / "winjob.py", ROOT / "requirements.txt"] + sorted(p for p in (ROOT / "solvers").rglob("*") if p.suffix in (".py", ".cpp", ".hpp", ".rs", ".java"))
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def runtime_versions():
    versions = {}
    for name, args in (("java", ["java", "-version"]), ("python", [PYTHON, "--version"])):
        result = call(args, capture_output=True)
        versions[name] = (result.stdout + result.stderr).strip()
    versions["packages"] = json.loads(call([PYTHON, "-c", "import importlib.metadata as m,json;print(json.dumps({p:m.version(p) for p in ('numpy','numba','llvmlite')}))"], capture_output=True).stdout)
    pinned = dict(line.split("==") for line in (ROOT / "requirements.txt").read_text().splitlines() if line)
    if versions["packages"] != pinned:
        raise RuntimeError("Las dependencias cambiaron; ejecuta python bench.py setup")
    return versions


def build():
    (ROOT / "build/java").mkdir(parents=True, exist_ok=True)
    rustc = str(RUSTC) if RUSTC.exists() else shutil.which("rustc")
    if not rustc or not PYTHON.exists():
        raise RuntimeError("Ejecuta primero: python bench.py setup")
    commands = [
        ["g++", "-std=c++20", "-O3", "-DNDEBUG", "-static-libgcc", "-static-libstdc++", ROOT / "solvers/cpp/main.cpp", "-o", ROOT / "build/cpp.exe"],
        [rustc, "--edition=2024", "-O", "-C", "lto=yes", "-C", "codegen-units=1", ROOT / "solvers/rust/main.rs", "-o", ROOT / "build/rust.exe"],
        ["javac", "--release", "17", "-encoding", "UTF-8", "-d", ROOT / "build/java", *sorted((ROOT / "solvers/java").glob("*.java"))],
    ]
    for command in commands:
        call(command, env=rust_env())
    versions = {}
    for name, command in {"cpp": ["g++", "--version"], "rust": [rustc, "--version"]}.items():
        result = call(command, env=rust_env(), capture_output=True)
        versions[name] = (result.stdout + result.stderr).strip()
    versions.update(runtime_versions())
    versions["commands"] = [list(map(str, command)) for command in commands]
    versions["source_hash"] = fingerprint()
    (ROOT / "build/versions.json").write_text(json.dumps(versions, indent=2), encoding="utf-8")
    return versions


def command(language):
    if language in ("cpp", "rust"):
        return [str(ROOT / f"build/{language}.exe")]
    if language == "java":
        return ["java", "-cp", str(ROOT / "build/java"), "Solver"]
    return [str(PYTHON), str(ROOT / "solvers/python/main.py")] + (["--numba"] if language == "numba" else [])


def read_instance(path):
    path = Path(path)
    if path.stat().st_size > 1048576:
        raise ValueError("Archivo demasiado grande")
    rows = [list(map(int, line.split())) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if not rows or len(rows[0]) != 2:
        raise ValueError("Cabecera incorrecta")
    n, m = rows[0]
    if n < 1 or m < 1 or n * m > 10000 or len(rows) != n + 1:
        raise ValueError("Dimensiones incorrectas")
    if any(len(row) != 2 * m or row[::2] != list(range(m)) or min(row[1::2]) < 0 for row in rows[1:]):
        raise ValueError("Operaciones incorrectas")
    p = [row[1::2] for row in rows[1:]]
    if max(map(max, p)) * n * (n + m) > 2**63 - 1:
        raise ValueError("Posible desbordamiento int64")
    return p


def flowtime(p, sequence):
    machines = [0] * len(p[0])
    total = 0
    for job in sequence:
        for machine, duration in enumerate(p[job - 1]):
            machines[machine] = max(machines[machine], machines[machine - 1] if machine else 0) + duration
        total += machines[-1]
    return total


def verify(result, p, algorithm, seed, evaluations=None):
    if not isinstance(result, dict) or set(result) != RESULT_FIELDS or result.get("algorithm") != algorithm or type(result.get("seed")) is not int or result["seed"] != seed:
        raise ValueError("Identidad de ejecución incorrecta")
    for sequence_key, cost_key, mean_key in (("reference_sequence", "reference_cost", "fmed_reference"), ("initial_sequence", "initial_cost", "fmed_initial"), ("sequence", "cost", "fmed_final")):
        sequence = result.get(sequence_key)
        if not isinstance(sequence, list) or any(type(job) is not int for job in sequence) or sorted(sequence) != list(range(1, len(p) + 1)):
            raise ValueError(f"Permutación incorrecta: {sequence_key}")
        cost = flowtime(p, sequence)
        mean = result.get(mean_key)
        if type(result.get(cost_key)) is not int or result[cost_key] != cost:
            raise ValueError(f"Coste incorrecto: {cost_key}")
        if type(mean) not in (int, float) or not math.isfinite(mean) or not math.isclose(mean, cost / len(p), rel_tol=1e-12, abs_tol=1e-9):
            raise ValueError(f"Fmed incorrecto: {mean_key}")
    if result["cost"] > min(result["reference_cost"], result["initial_cost"]):
        raise ValueError("Se perdió una solución mejor")
    count, checksum, cpu = result.get("evaluations"), result.get("cost_checksum"), result.get("cpu_seconds")
    if type(count) is not int or count < 0 or (evaluations is not None and count > evaluations):
        raise ValueError("Contador incorrecto")
    if type(checksum) is not int or not 0 <= checksum < 2**64 or type(cpu) not in (int, float) or not math.isfinite(cpu) or cpu < 0:
        raise ValueError("Métricas incorrectas")


def execute(language, algorithm, instance, seed, cpu=None, evaluations=None):
    args = command(language) + ["--algorithm", algorithm, "--instance", str(Path(instance).resolve()), "--seed", str(seed)]
    args += ["--cpu-budget", str(cpu)] if cpu is not None else ["--max-evaluations", str(evaluations)]
    record = {"language": language, "algorithm": algorithm, "seed": seed, "status": "ok"}
    start = time.perf_counter()
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        with winjob.start(args, ROOT, rust_env() | {"OPENBLAS_NUM_THREADS": "1", "NUMBA_NUM_THREADS": "1"}, out, err) as (job, process):
            try:
                while winjob.accounting(job).active:
                    if winjob.cpu(job) > (cpu + 3 if cpu is not None else 300) or time.perf_counter() - start > (max(180, cpu * 4) if cpu is not None else 600):
                        record["status"] = "timeout"
                        winjob.terminate(job)
                        break
                    time.sleep(0.02)
            except KeyboardInterrupt:
                record["status"] = "interrupted"
                winjob.terminate(job)
            while winjob.accounting(job).active: time.sleep(0.01)
            record["cpu_seconds"] = winjob.cpu(job)
            record["returncode"] = winjob.exit_code(process)
        record["wall_seconds"] = time.perf_counter() - start
        err.seek(0); stderr = err.read(16000).decode("utf-8", errors="replace")
        out.seek(0); stdout = out.read(1048577).decode("utf-8", errors="replace")
    if stderr:
        record["stderr"] = stderr
    if record["status"] != "ok":
        return record
    if record["returncode"]:
        record.update(status="crash", error=stderr or f"Código de salida {record['returncode']}")
        return record
    try:
        if len(stdout) > 1048576:
            raise ValueError("Salida demasiado grande")
        result = json.loads(stdout)
        json.dumps(result, allow_nan=False)
    except (ValueError, TypeError) as error:
        record.update(status="invalid_output", error=str(error), stdout=stdout[:2000])
        return record
    try:
        verify(result, read_instance(instance), algorithm, seed, evaluations)
        if result["cpu_seconds"] > record["cpu_seconds"] + 0.05:
            raise ValueError("CPU declarada superior a la CPU externa")
    except (ValueError, TypeError, KeyError) as error:
        record.update(status="invalid_solution", error=str(error), solver=result)
        return record
    measured = record["cpu_seconds"]
    record.update(result, cpu_seconds=measured, solver_cpu_seconds=result["cpu_seconds"])
    if cpu is not None and measured > cpu + 0.5:
        record.update(status="over_budget", error=f"CPU total {measured:.3f}s > presupuesto {cpu}s + margen de salida 0.5s")
    return record


def generate_instances(count):
    for kind, amount, first_seed in (("tuning", 5, 1001), ("validation", count, 2001)):
        folder = ROOT / "instances" / kind
        folder.mkdir(exist_ok=True)
        for i in range(amount):
            rng = random.Random(first_seed + i)
            text = "75 20\n" + "\n".join(" ".join(f"{machine} {rng.randint(1, 99)}" for machine in range(20)) for _ in range(75)) + "\n"
            path = folder / f"{i + 1:02}.txt"
            if path.exists() and path.read_text(encoding="utf-8") != text:
                raise RuntimeError(f"Instancia existente diferente: {path}")
            path.write_text(text, encoding="utf-8", newline="\n")
    return [ROOT / "instances/validation" / f"{i + 1:02}.txt" for i in range(count)]


def records(folder):
    path = Path(folder) / "runs.jsonl"
    result = {}
    if path.exists():
        for line in path.read_bytes().splitlines(keepends=True):
            if not line.endswith(b"\n"):
                break
            row = json.loads(line)
            result[row["id"]] = row
    return list(result.values())


def summarize(samples, expected):
    valid = [r for r in samples if r["status"] == "ok"]
    failed = len(samples) - len(valid)
    values = [r["fmed_final"] for r in valid]
    return {"status": "DESCARTADO" if failed else "COMPLETO" if len(samples) == expected else "PROVISIONAL",
            "runs": len(samples), "expected": expected, "failures": failed,
            "mean_initial": statistics.mean(r["fmed_initial"] for r in valid) if valid else None,
            "mean_final": statistics.mean(values) if values else None, "median": statistics.median(values) if values else None,
            "stddev": statistics.stdev(values) if len(values) > 1 else 0 if values else None,
            "minimum": min(values) if values else None, "maximum": max(values) if values else None,
            "mean_cpu": statistics.mean(r["cpu_seconds"] for r in samples), "mean_wall": statistics.mean(r["wall_seconds"] for r in samples),
            "mean_evaluations": statistics.mean(r["evaluations"] for r in valid) if valid else None}


def chart(items, label):
    if not items: return ""
    maximum = max(value for _, value, _ in items) or 1
    svg = f'<svg viewBox="0 0 900 {len(items) * 30 + 20}" role="img" aria-label="{label}">'
    for i, (name, value, status) in enumerate(sorted(items, key=lambda b: b[1])):
        y = 22 + i * 30
        color = "#166534" if status == "COMPLETO" else "#64748b" if status == "PROVISIONAL" else "#991b1b"
        svg += f'<text x="0" y="{y}">{html.escape(name)}</text><rect x="160" y="{y - 15}" width="{600 * value / maximum:.2f}" height="19" fill="{color}"/><text x="{170 + 600 * value / maximum:.2f}" y="{y}">{value:.2f}</text>'
    return svg + "</svg>"


def report(folder):
    folder = Path(folder)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    rows = records(folder)
    fields = ["phase", "instance", "language", "algorithm", "seed", "status", "fmed_reference", "fmed_initial", "fmed_final", "cpu_seconds", "wall_seconds", "evaluations", "error"]
    with (folder / "runs.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)
    groups, instance_groups = {}, {}
    for row in rows:
        groups.setdefault((row["phase"], row["language"], row["algorithm"]), []).append(row)
        instance_groups.setdefault((row["phase"], row["language"], row["algorithm"], row["instance"]), []).append(row)
    summary = []
    expected = manifest["config"]["instances"] * manifest["config"]["repetitions"]
    for (phase, language, algorithm), samples in sorted(groups.items()):
        summary.append({"phase": phase, "language": language, "algorithm": algorithm} | summarize(samples, expected))
    by_instance = [{"phase": phase, "language": language, "algorithm": algorithm, "instance": instance} | summarize(samples, manifest["config"]["repetitions"])
                   for (phase, language, algorithm, instance), samples in sorted(instance_groups.items())]
    (folder / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
    (folder / "by-instance.json").write_text(json.dumps(by_instance, indent=2, allow_nan=False), encoding="utf-8")
    def cell(value):
        return f"{value:.3f}" if isinstance(value, float) else "—" if value is None else html.escape(str(value))
    headers = ("Fase", "Lenguaje", "Algoritmo", "Estado", "n", "Fallos", "Fmed inicial", "Fmed final", "Mediana", "Desv.", "Mín.", "Máx.", "CPU (s)", "Real (s)", "Evaluaciones")
    body = []
    for row in summary:
        values = [row[k] for k in ("phase", "language", "algorithm", "status", "runs", "failures", "mean_initial", "mean_final", "median", "stddev", "minimum", "maximum", "mean_cpu", "mean_wall", "mean_evaluations")]
        body.append("<tr>" + "".join(f"<td>{cell(v)}</td>" for v in values) + "</tr>")
    quality_chart = chart([(f"{r['language']}/{r['algorithm']}", r["mean_final"], r["status"]) for r in summary if r["phase"] == "cpu" and r["mean_final"] is not None], "Fmed medio; menor es mejor")
    speed_chart = chart([(r["language"], r["mean_cpu"], r["status"]) for r in summary if r["phase"] == "baseline"], "CPU para 10000 permutaciones comunes; menor es mejor")
    eligible = sorted((r for r in summary if r["phase"] == "cpu" and r["status"] == "COMPLETO"), key=lambda r: (r["mean_final"], r["stddev"], r["language"], r["algorithm"]))
    ranking = "<ol>" + "".join(f"<li>{r['language']}/{r['algorithm']}: {r['mean_final']:.3f}</li>" for r in eligible) + "</ol>" if eligible else "<p>Pendiente de candidatos completos sin fallos.</p>"
    details = "".join("<tr>" + "".join(f"<td>{cell(row[k])}</td>" for k in ("instance", "phase", "language", "algorithm", "status", "runs", "mean_initial", "mean_final", "stddev", "minimum", "maximum")) + "</tr>" for row in by_instance)
    planned = expected * (len(manifest["config"]["languages"]) * len(manifest["config"]["algorithms"]) if manifest["config"]["phase"] == "cpu" else len(manifest["config"]["languages"]) if manifest["config"]["phase"] == "baseline" else len(manifest["config"]["languages"]) * (len(manifest["config"]["algorithms"]) + 1))
    document = f'''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OptContest</title>
<style>body{{font:16px system-ui;max-width:1400px;margin:32px auto;padding:0 20px;color:#172033;background:#f8fafc}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{padding:9px;text-align:right;border-bottom:1px solid #cbd5e1}}th:first-child,td:first-child{{text-align:left}}th{{background:#e2e8f0}}svg{{max-width:100%;font:14px system-ui}}.scroll{{overflow:auto}}a{{color:#1d4ed8}}pre{{white-space:pre-wrap}}</style>
<h1>OptContest</h1><p>{len(rows)} / {planned} ejecuciones registradas. {sum(r['status'] != 'ok' for r in rows)} fallos. Resultados provisionales hasta completar las muestras comunes.</p>
<p>CPU: proceso completo, incluido arranque y JIT. Baseline: exactamente 10 000 permutaciones comunes por instancia y semilla. Verde: completo; gris: provisional; rojo: descartado.</p>
<p><a href="runs.csv">CSV</a> · <a href="runs.jsonl">Ejecuciones y secuencias</a> · <a href="summary.json">Resumen JSON</a> · <a href="by-instance.json">Por instancia</a> · <a href="manifest.json">Entorno y parámetros</a></p>
<h2>Ranking elegible</h2>{ranking}<h2>Fmed final: menor es mejor</h2>{quality_chart}<h2>Velocidad del evaluador: CPU total</h2>{speed_chart}<h2>Comparación</h2><div class="scroll"><table><caption>Medias sobre las mismas instancias y semillas; n esperado: {expected}. Desviación conjunta entre instancias y repeticiones.</caption><thead><tr>{''.join('<th scope="col">'+h+'</th>' for h in headers)}</tr></thead><tbody>{''.join(body)}</tbody></table></div>
<details><summary>Resultados por instancia</summary><div class="scroll"><table><thead><tr>{''.join('<th scope="col">'+h+'</th>' for h in ('Instancia','Fase','Lenguaje','Algoritmo','Estado','n','Fmed inicial','Fmed final','Desv.','Mín.','Máx.'))}</tr></thead><tbody>{details}</tbody></table></div></details>
<h2>Entorno</h2><pre>{html.escape(json.dumps(manifest['host'], ensure_ascii=False, indent=2))}</pre><p>La campaña puede reanudarse con el mismo comando. El ranking definitivo utiliza únicamente candidatos completos sin fallos.</p></html>'''
    (folder / "report.html").write_text(document, encoding="utf-8")
    return summary


def run(args):
    versions_path = ROOT / "build/versions.json"
    versions = json.loads(versions_path.read_text(encoding="utf-8")) if versions_path.exists() else {}
    if versions.get("source_hash") != fingerprint():
        versions = build()
    else:
        versions.update(runtime_versions())
    instances = generate_instances(args.instances)
    folder = Path(args.results).resolve(); folder.mkdir(parents=True, exist_ok=True)
    config = {key: getattr(args, key) for key in ("instances", "repetitions", "cpu_budget", "languages", "algorithms", "phase")}
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in instances}
    host = {"platform": platform.platform(), "processor": platform.processor(), "logical_cpus": os.cpu_count()}
    cpu_name = call(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"], capture_output=True).stdout.strip()
    host["processor_name"] = cpu_name
    manifest = {"config": config, "instances": hashes, "host": host, "versions": versions}
    manifest_path = folder / "manifest.json"
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
            raise RuntimeError("Cambió el código, entorno o configuración; utiliza otra carpeta de resultados")
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    lock_path = ROOT / "results/.run.lock"; lock_path.parent.mkdir(exist_ok=True)
    with lock_path.open("a+b") as lock, winjob.awake():
        if lock.tell() == 0: lock.write(b"0"); lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        previous = records(folder)
        completed = {row["id"] for row in previous if row["status"] != "interrupted"}
        baseline_fields = ("reference_cost", "initial_cost", "cost", "reference_sequence", "sequence", "evaluations", "cost_checksum")
        baselines = {(row["instance_hash"], row["seed"]): [row[k] for k in baseline_fields]
                     for row in previous if row["phase"] == "baseline" and row["status"] == "ok"}
        path = folder / "runs.jsonl"
        if path.exists():
            data = path.read_bytes()
            if data and not data.endswith(b"\n"):
                with path.open("r+b") as file: file.truncate(data.rfind(b"\n") + 1)
        for repetition in range(args.repetitions):
            for instance_index, instance in enumerate(instances):
                jobs = [("baseline", language, "random") for language in args.languages] if args.phase != "cpu" else []
                if args.phase != "baseline":
                    matrix = list(itertools.product(args.languages, args.algorithms))
                    shift = (instance_index + repetition * len(instances)) % len(matrix)
                    matrix = matrix[shift:] + matrix[:shift]
                    if repetition % 2: matrix.reverse()
                    jobs += [("cpu", language, algorithm) for language, algorithm in matrix]
                for phase, language, algorithm in jobs:
                    key = f"{phase}:{instance_index + 1}:{language}:{algorithm}:{repetition + 1}"
                    if key in completed: continue
                    if fingerprint() != versions["source_hash"]:
                        raise RuntimeError("El código cambió durante la campaña; utiliza otra carpeta de resultados")
                    if hashlib.sha256(instance.read_bytes()).hexdigest() != hashes[str(instance.relative_to(ROOT))]:
                        raise RuntimeError("La instancia cambió durante la campaña")
                    print(f"{len(completed) + 1}: {key}", flush=True)
                    try:
                        row = execute(language, algorithm, instance, repetition + 1, args.cpu_budget if phase == "cpu" else None, 10000 if phase == "baseline" else None)
                        if phase == "baseline" and row["status"] == "ok" and row["evaluations"] != 10000:
                            row.update(status="invalid_solution", error="La referencia debe evaluar exactamente 10000 permutaciones")
                        if phase == "baseline" and row["status"] == "ok":
                            identity = (hashes[str(instance.relative_to(ROOT))], repetition + 1)
                            signature = [row[k] for k in baseline_fields]
                            if signature != baselines.setdefault(identity, signature):
                                row.update(status="invalid_solution", error="La referencia de 10000 permutaciones difiere entre lenguajes")
                    except KeyboardInterrupt:
                        return
                    row.update(id=key, phase=phase, instance=str(instance.relative_to(ROOT)), instance_hash=hashes[str(instance.relative_to(ROOT))])
                    with path.open("a", encoding="utf-8", newline="\n") as file:
                        file.write(json.dumps(row, allow_nan=False) + "\n"); file.flush(); os.fsync(file.fileno())
                    completed.add(key)
                    report(folder)
                    print(f"  {row['status']} Fmed={row.get('fmed_final', '—')} CPU={row['cpu_seconds']:.3f}s", flush=True)
                    if row["status"] == "interrupted": return
    print(f"Campaña terminada: {folder / 'report.html'}", flush=True)


def export(language, algorithm, team, destination=None):
    if not team.isascii() or not team.isalnum() or len(team) > 6:
        raise ValueError("El equipo debe contener de una a seis letras o cifras")
    team = f"{int(team):02}" if team.isdigit() else team
    name = f"optcontest{team}"
    folder = Path(destination) if destination else ROOT / "submission" / f"{language}-{algorithm}-{team}"
    folder.mkdir(parents=True, exist_ok=False)
    module = MODULES[algorithm]
    source = ROOT / "solvers" / ("python" if language == "numba" else language)
    if language == "cpp":
        files = ["core.hpp", f"{module}.hpp"]
        entry = f'#include "{module}.hpp"\nint main(int argc, char** argv) {{ return run(argc, argv, {module if algorithm in ("random", "local") else algorithm}, "{algorithm}", true); }}\n'
        (folder / f"{name}.cpp").write_text(entry, encoding="utf-8")
        instructions = f"g++ -std=c++20 -O3 -DNDEBUG -static-libgcc -static-libstdc++ {name}.cpp -o {name}.exe\n.\\{name}.exe"
    elif language == "rust":
        files = ["core.rs", f"{module}.rs"]
        (folder / f"{name}.rs").write_text(f'mod core;\nmod {module};\nfn main() {{ core::run({module}::solve, "{algorithm}", true); }}\n', encoding="utf-8")
        instructions = f"rustc --edition=2024 -O {name}.rs -o {name}.exe\n.\\{name}.exe"
    elif language == "java":
        cls = JAVA_CLASSES[algorithm]
        files = ["Core.java", f"{cls}.java"]
        (folder / f"{name}.java").write_text(f'public final class {name} {{\n    public static void main(String[] args) {{ Core.run(args, {cls}::solve, "{algorithm}", true); }}\n}}\n', encoding="utf-8")
        instructions = f"javac --release 17 -encoding UTF-8 *.java\njava {name}"
    else:
        files = ["core.py", "main.py", f"{module}.py"]
        prefix = 'import sys\nsys.argv.append("--numba")\n' if language == "numba" else ""
        (folder / f"{name}.py").write_text(prefix + f'from main import main\nmain("{algorithm}", True, {language == "numba"})\n', encoding="utf-8")
        requirements = (ROOT / "requirements.txt").read_text() if language == "numba" else "numpy==2.5.1\n"
        (folder / "requirements.txt").write_text(requirements, encoding="utf-8")
        instructions = f"python -m pip install -r requirements.txt\npython {name}.py"
    for file in files: shutil.copyfile(source / file, folder / file)
    shutil.copyfile(ROOT / "LICENSE", folder / "LICENSE")
    (folder / "leeme.txt").write_text(f"Windows 11 x64. {language}/{algorithm}.\nColoca test.txt junto al programa y ejecuta desde esta carpeta:\n\n{instructions}\n\nSalida: Fmed, segundos de CPU y secuencia (órdenes desde 1), en tres líneas.\nPresupuesto interno: 57 s de CPU del proceso, incluido arranque e inicialización.\n", encoding="utf-8")
    return folder.resolve()


def main():
    parser = argparse.ArgumentParser(description="OptContest: comparar, verificar y exportar")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("setup"); commands.add_parser("build"); commands.add_parser("check")
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--instances", type=int, default=10)
    run_parser.add_argument("--repetitions", type=int, default=5)
    run_parser.add_argument("--cpu-budget", type=float, default=57)
    run_parser.add_argument("--languages", nargs="+", choices=LANGUAGES, default=list(LANGUAGES))
    run_parser.add_argument("--algorithms", nargs="+", choices=ALGORITHMS, default=list(ALGORITHMS))
    run_parser.add_argument("--phase", choices=("all", "cpu", "baseline"), default="all")
    run_parser.add_argument("--results", default=str(ROOT / "results/full"))
    report_parser = commands.add_parser("report"); report_parser.add_argument("folder", type=Path)
    export_parser = commands.add_parser("export")
    export_parser.add_argument("--language", choices=LANGUAGES, required=True)
    export_parser.add_argument("--algorithm", choices=ALGORITHMS, required=True)
    export_parser.add_argument("--team", required=True)
    export_parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    if args.action == "setup": setup()
    elif args.action == "build": build()
    elif args.action == "check": build(); call([PYTHON, ROOT / "check.py"])
    elif args.action == "run":
        if not 1 <= args.instances <= 1000 or not 1 <= args.repetitions <= 10000 or not math.isfinite(args.cpu_budget) or args.cpu_budget <= 0 or len(set(args.languages)) != len(args.languages) or len(set(args.algorithms)) != len(args.algorithms):
            parser.error("Configuración incorrecta")
        run(args)
    elif args.action == "report": report(args.folder)
    elif args.action == "export": print(export(args.language, args.algorithm, args.team, args.destination))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
