#!/usr/bin/env python3
"""
Consolidador Avanzado de Dataset para Entrenamiento de Modelo Readahead
Extrae features desde trazas LTTng y usa métricas FIO reales como targets
"""

import re
import csv
import json
import statistics
import sys
from pathlib import Path
from collections import defaultdict, Counter
import multiprocessing as mp

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

PROJECT_DIR = Path.home() / "kml-project"
TRACES_DIR = PROJECT_DIR / "traces" / "training"

# Verificar que el directorio existe
if not TRACES_DIR.exists():
    # Intentar rutas alternativas
    alt_paths = [
        Path.home() / "kml_project" / "traces" / "training",
        Path("/root/kml-project/traces/training"),
        Path("/root/kml_project/traces/training"),
    ]
    for alt in alt_paths:
        if alt.exists():
            TRACES_DIR = alt
            PROJECT_DIR = alt.parent.parent
            break
OUTPUT_FILE = None  # Se configurará después de encontrar TRACES_DIR
WINDOW_SIZE = 0.5  # segundos
MIN_EVENTS_PER_WINDOW = 5

# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

def parse_timestamp(ts_str):
    """Parsea timestamp en formato [HH:MM:SS.nanosec]"""
    match = re.match(r'\[(\d+):(\d+):(\d+)\.(\d+)\]', ts_str)
    if match:
        h, m, s, ns = map(int, match.groups())
        return h * 3600 + m * 60 + s + ns / 1_000_000_000
    return None


def calculate_sequentiality(offsets):
    """
    Calcula qué tan secuencial es un patrón de acceso.
    Retorna un valor entre 0 (random) y 1 (secuencial)
    """
    if len(offsets) < 2:
        return 0.0
    
    diffs = [offsets[i+1] - offsets[i] for i in range(len(offsets)-1)]
    
    # Contar accesos consecutivos (diferencias pequeñas y positivas)
    positive_consecutive = sum(1 for d in diffs if 0 < d < 10000)
    total_diffs = len(diffs)
    
    if total_diffs == 0:
        return 0.0
    
    sequentiality = positive_consecutive / total_diffs
    return sequentiality


def parse_babeltrace_line(line):
    """
    Parsea línea de babeltrace:
    [timestamp] (+delta) hostname event_name: { cpu_id = X }, { field = val, ... }
    """
    ts_match = re.match(r'\[(\d+:\d+:\d+\.\d+)\]', line)
    if not ts_match:
        return None
    
    timestamp = parse_timestamp(ts_match.group(1))
    if timestamp is None:
        return None
    
    event_match = re.search(r'\]\s+\(\+[^\)]+\)\s+\w+\s+([^:]+):', line)
    if not event_match:
        return None
    
    event_name = event_match.group(1).strip()
    
    fields = {}
    field_pattern = r'(\w+)\s*=\s*([^,\}]+)'
    for match in re.finditer(field_pattern, line):
        field_name = match.group(1).strip()
        field_value = match.group(2).strip()
        
        try:
            if '.' in field_value:
                fields[field_name] = float(field_value)
            else:
                fields[field_name] = int(field_value)
        except ValueError:
            fields[field_name] = field_value.strip('"')
    
    return {
        'timestamp': timestamp,
        'event_name': event_name,
        'fields': fields
    }


def parse_trace_file(trace_file):
    """Parsea trace.txt y extrae eventos de I/O"""
    events = []
    start_time = None
    
    io_events = {
        'block_rq_issue',
        'block_rq_insert', 
        'block_rq_complete',
        'block_bio_queue',
        'block_bio_remap',
        'block_getrq'
    }
    
    try:
        with open(trace_file, 'r', errors='ignore', buffering=1024*1024) as f:
            for line in f:
                parsed = parse_babeltrace_line(line)
                
                if not parsed:
                    continue
                
                timestamp = parsed['timestamp']
                event_name = parsed['event_name']
                fields = parsed['fields']
                
                if event_name not in io_events:
                    continue
                
                sector = fields.get('sector')
                if sector is None:
                    continue
                
                if start_time is None:
                    start_time = timestamp
                
                rel_time = timestamp - start_time
                
                event = {
                    'time': rel_time,
                    'type': event_name,
                    'offset': sector,
                    'size': fields.get('bytes', fields.get('nr_sector', 0)),
                    'dev': fields.get('dev', 0)
                }
                
                events.append(event)
        
        return events
    
    except Exception as e:
        print(f"  ⚠ Error parseando: {e}")
        return []


def extract_features_from_window(window_events, offsets):
    """Extrae features estadísticas de una ventana"""
    if len(offsets) < 2:
        return None
    
    diffs = [abs(offsets[i+1] - offsets[i]) for i in range(len(offsets)-1)]
    
    features = {
        'num_transactions': len(offsets),
        'mean_offset': statistics.mean(offsets),
        'std_offset': statistics.stdev(offsets) if len(offsets) > 1 else 0,
        'min_offset': min(offsets),
        'max_offset': max(offsets),
        'offset_range': max(offsets) - min(offsets),
    }
    
    if diffs:
        features.update({
            'mean_abs_diff': statistics.mean(diffs),
            'std_abs_diff': statistics.stdev(diffs) if len(diffs) > 1 else 0,
            'max_abs_diff': max(diffs),
            'min_abs_diff': min(diffs),
            'median_abs_diff': statistics.median(diffs),
        })
    else:
        features.update({
            'mean_abs_diff': 0,
            'std_abs_diff': 0,
            'max_abs_diff': 0,
            'min_abs_diff': 0,
            'median_abs_diff': 0,
        })
    
    features['sequentiality'] = calculate_sequentiality(offsets)
    
    event_counts = Counter([e['type'] for e in window_events])
    features['count_rq_issue'] = event_counts.get('block_rq_issue', 0)
    features['count_rq_insert'] = event_counts.get('block_rq_insert', 0)
    features['count_rq_complete'] = event_counts.get('block_rq_complete', 0)
    features['count_bio_queue'] = event_counts.get('block_bio_queue', 0)
    
    total_events = sum(event_counts.values())
    if total_events > 0:
        features['ratio_rq_issue'] = event_counts.get('block_rq_issue', 0) / total_events
        features['ratio_bio_queue'] = event_counts.get('block_bio_queue', 0) / total_events
    else:
        features['ratio_rq_issue'] = 0
        features['ratio_bio_queue'] = 0
    
    return features


def extract_features(events, pattern, run_id, cache_state):
    """Extrae features ventana a ventana"""
    if not events:
        return []
    
    features_list = []
    max_time = events[-1]['time']
    num_windows = int(max_time / WINDOW_SIZE) + 1
    
    for idx in range(num_windows):
        w_start = idx * WINDOW_SIZE
        w_end = (idx + 1) * WINDOW_SIZE
        
        window_events = [e for e in events if w_start <= e['time'] < w_end]
        
        if len(window_events) < MIN_EVENTS_PER_WINDOW:
            continue
        
        offsets = [e['offset'] for e in window_events]
        
        if len(offsets) < 2:
            continue
        
        window_features = extract_features_from_window(window_events, offsets)
        
        if window_features is None:
            continue
        
        row = {
            'run_id': run_id,
            'pattern': pattern,
            'cache_state': cache_state,
            'window_idx': idx,
            'time_start': round(w_start, 3),
            'time_end': round(w_end, 3),
            **window_features
        }
        
        features_list.append(row)
    
    return features_list


def load_fio_metrics(run_dir):
    """Carga métricas FIO como target del modelo"""
    json_file = run_dir / "fio_output.json"
    
    if not json_file.exists():
        return {}
    
    try:
        with open(json_file) as f:
            data = json.load(f)
        
        job = data['jobs'][0]
        read_data = job.get('read', {})
        
        # Métricas de rendimiento observadas
        metrics = {
            'fio_iops': read_data.get('iops', 0),
            'fio_bw_kbps': read_data.get('bw', 0),
            'fio_lat_mean_us': read_data.get('lat', {}).get('mean', 0),
            'fio_lat_stddev_us': read_data.get('lat', {}).get('stddev', 0),
            'fio_clat_mean_us': read_data.get('clat', {}).get('mean', 0),
        }
        
        return metrics
    
    except Exception as e:
        print(f"  ⚠ Error cargando FIO: {e}")
        return {}


def process_single_run(args):
    """Procesa un run individual"""
    run_dir, pattern = args
    run_id = run_dir.name
    cache_state = 'cold' if 'cold' in run_id else 'warm'
    
    trace_file = run_dir / "trace.txt"
    
    if not trace_file.exists():
        return []
    
    file_size_mb = trace_file.stat().st_size / (1024**2)
    print(f"  → {pattern}/{run_id} ({file_size_mb:.1f} MB)")
    
    events = parse_trace_file(trace_file)
    
    if not events:
        print(f"    ⚠ Sin eventos I/O")
        return []
    
    print(f"    ✓ {len(events):,} eventos")
    
    features = extract_features(events, pattern, run_id, cache_state)
    
    if not features:
        print(f"    ⚠ Sin features")
        return []
    
    print(f"    ✓ {len(features):,} ventanas")
    
    fio_metrics = load_fio_metrics(run_dir)
    
    for f in features:
        f.update(fio_metrics)
    
    return features


# ============================================================================
# CONSOLIDACIÓN PRINCIPAL
# ============================================================================

def consolidate_dataset():
    """Función principal"""
    print("=" * 80)
    print("CONSOLIDACIÓN DE DATASET PARA ENTRENAMIENTO")
    print("=" * 80)
    print(f"Directorio: {TRACES_DIR}")
    print(f"Ventana: {WINDOW_SIZE}s | Min eventos: {MIN_EVENTS_PER_WINDOW}")
    print("=" * 80)
    
    patterns = ['sequential', 'random', 'mixed']
    runs_to_process = []
    
    for pattern in patterns:
        pattern_dir = TRACES_DIR / pattern
        
        if not pattern_dir.exists():
            print(f"⚠ {pattern} no encontrado")
            continue
        
        runs = sorted([r for r in pattern_dir.iterdir() if r.is_dir()])
        
        print(f"\n{pattern.upper()}: {len(runs)} runs")
        
        for run_dir in runs:
            runs_to_process.append((run_dir, pattern))
    
    if not runs_to_process:
        print("\n⚠ No hay runs para procesar!")
        return
    
    print(f"\nTotal runs: {len(runs_to_process)}\n")
    
    num_workers = max(1, mp.cpu_count() - 1)
    print(f"Workers paralelos: {num_workers}\n")
    
    with mp.Pool(num_workers) as pool:
        results = pool.map(process_single_run, runs_to_process)
    
    all_rows = []
    for result in results:
        all_rows.extend(result)
    
    if not all_rows:
        print("\n⚠ No se generaron features!")
        return
    
    print("\n" + "="*80)
    print("GUARDANDO DATASET")
    print("="*80)
    
    fieldnames = [
        'run_id', 'pattern', 'cache_state', 'window_idx',
        'time_start', 'time_end',
        'num_transactions', 'mean_offset', 'std_offset',
        'min_offset', 'max_offset', 'offset_range',
        'mean_abs_diff', 'std_abs_diff', 'max_abs_diff', 
        'min_abs_diff', 'median_abs_diff',
        'sequentiality',
        'count_rq_issue', 'count_rq_insert', 'count_rq_complete', 
        'count_bio_queue', 'ratio_rq_issue', 'ratio_bio_queue',
        'fio_iops', 'fio_bw_kbps', 'fio_lat_mean_us', 
        'fio_lat_stddev_us', 'fio_clat_mean_us'
    ]
    
    with open(OUTPUT_FILE, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(all_rows)
    
    total = len(all_rows)
    file_size_mb = OUTPUT_FILE.stat().st_size / (1024**2)
    
    print(f"\n✓ Dataset consolidado!")
    print(f"  Muestras: {total:,}")
    print(f"  Tamaño: {file_size_mb:.2f} MB")
    print(f"\nDistribución por patrón:")
    
    dist = defaultdict(int)
    cache_dist = defaultdict(lambda: defaultdict(int))
    
    for r in all_rows:
        dist[r['pattern']] += 1
        cache_dist[r['pattern']][r['cache_state']] += 1
    
    for p in sorted(dist.keys()):
        count = dist[p]
        pct = count / total * 100
        cold = cache_dist[p]['cold']
        warm = cache_dist[p]['warm']
        print(f"  {p:12s}: {count:8,} ({pct:5.1f}%) - cold: {cold:,} | warm: {warm:,}")
    
    print(f"\n✓ Guardado en: {OUTPUT_FILE}")
    print("="*80)
    print("\nNOTA: Este dataset contiene features + métricas de rendimiento FIO.")
    print("Para entrenar, puedes usar las métricas FIO como targets o definir")
    print("tus propios targets basados en el patrón y rendimiento observado.")
    print("="*80)


if __name__ == "__main__":
    try:
        consolidate_dataset()
    except KeyboardInterrupt:
        print("\n\n⚠ Interrumpido")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
