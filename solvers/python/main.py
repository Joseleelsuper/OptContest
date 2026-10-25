import argparse
import importlib
import json
import math
from pathlib import Path
import secrets
import sys

import numpy as np

from core import NUMBA, Search

ALGORITHMS = ("random", "local", "sa", "ga", "ig")


def read_instance(path):
    if Path(path).stat().st_size > 1048576:
        raise ValueError("Archivo demasiado grande")
    lines = [line.split() for line in Path(path).read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if not lines or len(lines[0]) != 2:
        raise ValueError("Cabecera esperada: n m")
    n, m = map(int, lines[0])
    if n < 1 or m < 1 or n * m > 10000 or len(lines) != n + 1:
        raise ValueError("Dimensiones o número de filas incorrectos (máximo 10000 operaciones)")
    rows = []
    for line in lines[1:]:
        values = list(map(int, line))
        if len(values) != 2 * m or values[::2] != list(range(m)) or min(values[1::2]) < 0:
            raise ValueError("Fila de pares máquina-duración incorrecta")
        rows.append(values[1::2])
    if max(map(max, rows)) * n * (n + m) > 9223372036854775807:
        raise ValueError("La instancia puede desbordar int64")
    return np.array(rows, dtype=np.int64)


def main(algorithm=None, contest=False, numba=False):
    parser = argparse.ArgumentParser()
    parser.add_argument("--algorithm", choices=(algorithm,) if algorithm else ALGORITHMS, default=algorithm or "ig")
    parser.add_argument("--instance", default="test.txt")
    parser.add_argument("--seed", type=int)
    limit = parser.add_mutually_exclusive_group()
    limit.add_argument("--cpu-budget", type=float)
    limit.add_argument("--max-evaluations", type=int)
    parser.add_argument("--output", choices=("json",), default="json")
    parser.add_argument("--contest", action="store_true", default=contest)
    parser.add_argument("--numba", action="store_true", default=numba)
    args = parser.parse_args()
    cpu_limit = args.cpu_budget if args.cpu_budget is not None else (86400.0 if args.max_evaluations else 57.0)
    evaluations = args.max_evaluations if args.max_evaluations is not None else 9223372036854775807
    seed = secrets.randbits(64) if args.seed is None else args.seed
    if not math.isfinite(cpu_limit) or cpu_limit <= 0 or not 1 <= evaluations <= 9223372036854775807 or not 0 <= seed < 2**64:
        raise ValueError("Presupuesto o semilla incorrectos")
    if args.numba != NUMBA:
        raise ValueError("La modalidad Numba debe seleccionarse antes de importar core")
    processing = read_instance(args.instance)
    if NUMBA and args.max_evaluations is None:
        cpu_limit = max(0.0, cpu_limit - 1.0)  # Reserva CPU para la salida y el cierre de LLVM.
    search = Search(processing, np.uint64(seed), cpu_limit, evaluations)
    module = {"random": "random_search", "local": "local_search"}.get(args.algorithm, args.algorithm)
    solve = importlib.import_module(module).solve
    if NUMBA:
        from numba import njit

        solve = njit(solve)
    solve(search)
    result = {
        "algorithm": args.algorithm, "seed": seed, "reference_cost": int(search.reference_cost),
        "initial_cost": int(search.initial_cost), "cost": int(search.best_cost),
        "fmed_reference": search.reference_cost / search.n,
        "fmed_initial": search.initial_cost / search.n, "fmed_final": search.best_cost / search.n,
        "reference_sequence": (search.reference + 1).tolist(),
        "initial_sequence": (search.initial + 1).tolist(), "sequence": (search.best + 1).tolist(),
        "evaluations": int(search.evaluations), "cost_checksum": int(search.checksum), "cpu_seconds": search.cpu(),
    }
    if args.contest:
        print(f"{result['fmed_final']:.10f}\n{result['cpu_seconds']:.6f}\n" + " ".join(map(str, result["sequence"])))
    else:
        print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
