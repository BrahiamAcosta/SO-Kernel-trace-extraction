#!/usr/bin/env python3
"""
Consolidador Avanzado de Dataset para Entrenamiento de Modelo Readahead
Extrae features ricas desde trazas LTTng y métricas FIO (multi-run).
"""

import re
import csv
import json
import statistics
from pathlib import Path
from collections import defaultdict

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

PROJECT_DIR = Path.home() / "kml-project"
TRACES_DIR = PROJECT_DIR / "traces" / "training"
OUTPUT_FILE = PROJECT_DIR / "traces" / "training_dataset_full.csv"
WINDOW_SIZE = 1.0  # segundos

# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

def parse_timestamp(ts_str):
    match = re.match(r'\[(\d+):(\d+):(\d+)\.(\d+)\]', ts_str)
    if match:
        h, m, s, us = map(int, match.groups())
        return h * 3600 + m * 60 + s + us / 1_000_000
    return 0.0


def parse_trace_file(trace_file, pattern, run_id, cache_state):
    """Parsea trace.txt y devuelve lista de eventos con campos relevantes"""
    events = []
    start_time = None

    with open(trace_file, 'r', errors="ignore") as f:
        for line_num, line in enumerate(f, 1):
            ts_match = re.match(r'\[(\d+:\d+:\d+\.\d+)\]', line)
            if not ts_match:
                continue

            timestamp = parse_timestamp(ts_match.group(1))
            if start_time is None:
                start_time = timestamp
            rel_time = timestamp - start_time

            ev = {
                "time": rel_time,
                "pattern": pattern,
                "run_id": run_id,
                "cache_state": cache_state,
                "type": None,
                "offset": None,
                "size": None
            }

            if "mm_filemap_add_to_page_cache" in line:
                ev["type"] = "page_add"
                off = re.search(r"index = (\d+)", line)
                if off:
                    ev["offset"] = int(off.group(1))
            elif "block_rq_issue" in line or "block_rq_insert" in line:
                ev["type"] = "block_io"
                off = re.search(r"sector = (\d+)", line)
                if off:
                    ev["offset"] = int(off.group(1))
            elif "syscall_entry_read" in line or "syscall_entry_pread64" in line:
                ev["type"] = "syscall_read"
                sz = re.search(r"count = (\d+)", line)
                if sz:
                    ev["size"] = int(sz.group(1))

            if ev["type"]:
                events.append(ev)

    return events


def extract_features(events, pattern, run_id, cache_state):
    """Extrae features ventana a ventana"""
    if not events:
        return []

    features = []
    max_time = events[-1]["time"]
    num_windows = int(max_time / WINDOW_SIZE) + 1

    for idx in range(num_windows):
        w_start, w_end = idx * WINDOW_SIZE, (idx + 1) * WINDOW_SIZE
        window_events = [e for e in events if w_start <= e["time"] < w_end and e["offset"] is not None]
        if len(window_events) < 2:
            continue

        offsets = [e["offset"] for e in window_events]
        diffs = [abs(offsets[i+1] - offsets[i]) for i in range(len(offsets)-1)]

        num_transactions = len(offsets)
        mean_offset = statistics.mean(offsets)
        std_offset = statistics.stdev(offsets) if len(offsets) > 1 else 0
        mean_abs_diff = statistics.mean(diffs)
        max_abs_diff = max(diffs)

        optimal_readahead = {"sequential": 1024, "random": 8, "mixed": 256}

        row = {
            "run_id": run_id,
            "pattern": pattern,
            "cache_state": cache_state,
            "window_idx": idx,
            "time_start": round(w_start, 2),
            "time_end": round(w_end, 2),
            "num_transactions": num_transactions,
            "mean_offset": mean_offset,
            "std_offset": std_offset,
            "mean_abs_diff": mean_abs_diff,
            "max_abs_diff": max_abs_diff,
            "target_readahead": optimal_readahead.get(pattern, 256)
        }
        features.append(row)
    return features


def load_fio_metrics(run_dir):
    """Carga métricas globales de FIO desde los archivos JSON"""
    json_file = run_dir / "fio_output.json"
    if not json_file.exists():
        return {}
    try:
        with open(json_file) as f:
            data = json.load(f)
        job = data["jobs"][0]
        return {
            "iops": job["read"]["iops"],
            "bw_kbps": job["read"]["bw"],
            "lat_mean_us": job["read"]["lat"]["mean"],
            "lat_std_us": job["read"]["lat"]["stddev"],
            "slat_mean_us": job["read"]["slat"]["mean"],
            "clat_mean_us": job["read"]["clat"]["mean"],
        }
    except Exception:
        return {}


# ============================================================================
# CONSOLIDACIÓN PRINCIPAL
# ============================================================================

def consolidate_dataset():
    print("="*80)
    print("CONSOLIDACIÓN AVANZADA DE DATASET MULTI-RUN")
    print("="*80)

    all_rows = []
    patterns = ["sequential", "random", "mixed"]

    for pattern in patterns:
        pattern_dir = TRACES_DIR / pattern
        if not pattern_dir.exists():
            continue
        runs = [r for r in pattern_dir.iterdir() if r.is_dir()]

        for run_dir in runs:
            run_id = run_dir.name
            cache_state = "cold" if "cold" in run_id else "warm"
            trace_file = run_dir / "trace.txt"
            if not trace_file.exists():
                continue

            print(f"→ Procesando {pattern}/{run_id}")
            events = parse_trace_file(trace_file, pattern, run_id, cache_state)
            feats = extract_features(events, pattern, run_id, cache_state)
            fio = load_fio_metrics(run_dir)

            # Enriquecer cada ventana con métricas de FIO
            for f in feats:
                f.update(fio)
            all_rows.extend(feats)

    # ------------------------------------------------------------------------
    # Guardar CSV
    # ------------------------------------------------------------------------
    if not all_rows:
        print("⚠ No se generaron features. Verifica las trazas.")
        return

    fieldnames = [
        "run_id", "pattern", "cache_state", "window_idx",
        "time_start", "time_end", "num_transactions",
        "mean_offset", "std_offset", "mean_abs_diff", "max_abs_diff",
        "iops", "bw_kbps", "lat_mean_us", "lat_std_us",
        "slat_mean_us", "clat_mean_us", "target_readahead"
    ]

    with open(OUTPUT_FILE, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    # ------------------------------------------------------------------------
    # Estadísticas
    # ------------------------------------------------------------------------
    total = len(all_rows)
    print(f"\n✓ Dataset consolidado con {total:,} muestras")
    dist = defaultdict(int)
    for r in all_rows:
        dist[r["pattern"]] += 1

    for p, c in dist.items():
        print(f"  {p:12s}: {c:8d} ({c/total*100:5.1f}%)")

    print(f"\nArchivo guardado: {OUTPUT_FILE}")


if __name__ == "__main__":
    consolidate_dataset()
