#!/usr/bin/env python3
"""
Consolidador Avanzado de Dataset para Entrenamiento de Modelo Readahead
Extrae features ricas desde trazas LTTng y métricas FIO (multi-run).
Versión optimizada para procesar datasets grandes (18GB+)
"""

import re
import csv
import json
import statistics
import sys
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime
import multiprocessing as mp
from functools import partial

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

PROJECT_DIR = Path.home() / "kml-project"
TRACES_DIR = PROJECT_DIR / "traces" / "training"
OUTPUT_FILE = PROJECT_DIR / "traces" / "training_dataset_full.csv"
WINDOW_SIZE = 0.5  # segundos (ventanas más pequeñas = más muestras)
MIN_EVENTS_PER_WINDOW = 3  # mínimo de eventos para considerar una ventana válida

# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

def parse_timestamp(ts_str):
    """Parsea timestamp en formato [HH:MM:SS.microsec]"""
    match = re.match(r'\[(\d+):(\d+):(\d+)\.(\d+)\]', ts_str)
    if match:
        h, m, s, us = map(int, match.groups())
        return h * 3600 + m * 60 + s + us / 1_000_000
    return None


def calculate_sequentiality(offsets):
    """
    Calcula qué tan secuencial es un patrón de acceso.
    Retorna un valor entre 0 (completamente random) y 1 (completamente secuencial)
    """
    if len(offsets) < 2:
        return 0.0
    
    diffs = [offsets[i+1] - offsets[i] for i in range(len(offsets)-1)]
    
    # Si todos los diffs son positivos y similares -> secuencial
    positive_diffs = [d for d in diffs if d > 0]
    if not positive_diffs:
        return 0.0
    
    # Coeficiente de variación de los diffs positivos
    mean_diff = statistics.mean(positive_diffs)
    if mean_diff == 0:
        return 0.0
    
    std_diff = statistics.stdev(positive_diffs) if len(positive_diffs) > 1 else 0
    cv = std_diff / mean_diff if mean_diff > 0 else 0
    
    # Sequentiality score: bajo CV = más secuencial
    sequentiality = max(0, 1 - min(cv, 1))
    
    return sequentiality


def parse_trace_file(trace_file):
    """
    Parsea trace.txt y devuelve lista de eventos con timestamps y offsets.
    Optimizado para procesar archivos grandes.
    """
    events = []
    start_time = None
    
    # Patrones de regex precompilados para mejor performance
    ts_pattern = re.compile(r'\[(\d+:\d+:\d+\.\d+)\]')
    sector_pattern = re.compile(r'sector\s*=\s*(\d+)')
    index_pattern = re.compile(r'index\s*=\s*(\d+)')
    count_pattern = re.compile(r'count\s*=\s*(\d+)')
    
    event_types = {
        'block_rq_issue': 'block_io',
        'block_rq_insert': 'block_io',
        'block_rq_complete': 'block_complete',
        'mm_filemap_add_to_page_cache': 'page_add',
        'syscall_entry_read': 'syscall_read',
        'syscall_entry_pread64': 'syscall_read',
        'syscall_entry_readv': 'syscall_read',
        'syscall_entry_preadv': 'syscall_read',
    }
    
    try:
        with open(trace_file, 'r', errors='ignore', buffering=1024*1024) as f:
            for line in f:
                # Extraer timestamp
                ts_match = ts_pattern.search(line)
                if not ts_match:
                    continue
                
                timestamp = parse_timestamp(ts_match.group(1))
                if timestamp is None:
                    continue
                
                if start_time is None:
                    start_time = timestamp
                
                rel_time = timestamp - start_time
                
                # Identificar tipo de evento
                event_type = None
                for key, val in event_types.items():
                    if key in line:
                        event_type = val
                        break
                
                if not event_type:
                    continue
                
                # Extraer offset (sector o page index)
                offset = None
                sector_match = sector_pattern.search(line)
                if sector_match:
                    offset = int(sector_match.group(1))
                else:
                    index_match = index_pattern.search(line)
                    if index_match:
                        offset = int(index_match.group(1)) * 8  # page index -> sectors aprox
                
                # Extraer tamaño si está disponible
                size = None
                count_match = count_pattern.search(line)
                if count_match:
                    size = int(count_match.group(1))
                
                if offset is not None:
                    events.append({
                        'time': rel_time,
                        'type': event_type,
                        'offset': offset,
                        'size': size
                    })
        
        return events
    
    except Exception as e:
        print(f"  ⚠ Error parseando {trace_file}: {e}")
        return []


def extract_features_from_window(window_events, offsets):
    """Extrae features estadísticas de una ventana de eventos"""
    if len(offsets) < 2:
        return None
    
    # Diferencias consecutivas
    diffs = [abs(offsets[i+1] - offsets[i]) for i in range(len(offsets)-1)]
    
    # Features básicas
    features = {
        'num_transactions': len(offsets),
        'mean_offset': statistics.mean(offsets),
        'std_offset': statistics.stdev(offsets) if len(offsets) > 1 else 0,
        'min_offset': min(offsets),
        'max_offset': max(offsets),
        'offset_range': max(offsets) - min(offsets),
    }
    
    # Features de diferencias (distancias entre accesos)
    if diffs:
        features.update({
            'mean_abs_diff': statistics.mean(diffs),
            'std_abs_diff': statistics.stdev(diffs) if len(diffs) > 1 else 0,
            'max_abs_diff': max(diffs),
            'min_abs_diff': min(diffs),
            'median_abs_diff': statistics.median(diffs),
        })
    
    # Sequentiality score
    features['sequentiality'] = calculate_sequentiality(offsets)
    
    # Conteo de tipos de eventos
    event_counts = Counter([e['type'] for e in window_events])
    features['count_block_io'] = event_counts.get('block_io', 0)
    features['count_page_add'] = event_counts.get('page_add', 0)
    features['count_syscall'] = event_counts.get('syscall_read', 0)
    
    # Ratio de eventos
    total_events = sum(event_counts.values())
    if total_events > 0:
        features['ratio_block_io'] = event_counts.get('block_io', 0) / total_events
        features['ratio_page_add'] = event_counts.get('page_add', 0) / total_events
    
    return features


def extract_features(events, pattern, run_id, cache_state):
    """Extrae features ventana a ventana desde eventos parseados"""
    if not events:
        return []
    
    features_list = []
    max_time = events[-1]['time']
    num_windows = int(max_time / WINDOW_SIZE) + 1
    
    for idx in range(num_windows):
        w_start = idx * WINDOW_SIZE
        w_end = (idx + 1) * WINDOW_SIZE
        
        # Filtrar eventos en esta ventana
        window_events = [e for e in events if w_start <= e['time'] < w_end]
        
        if len(window_events) < MIN_EVENTS_PER_WINDOW:
            continue
        
        # Extraer offsets
        offsets = [e['offset'] for e in window_events if e['offset'] is not None]
        
        if len(offsets) < 2:
            continue
        
        # Extraer features estadísticas
        window_features = extract_features_from_window(window_events, offsets)
        
        if window_features is None:
            continue
        
        # Target: valor óptimo de readahead según el patrón
        # Estos valores son heurísticos basados en práctica común
        optimal_readahead = {
            'sequential': 2048,  # KB - lecturas grandes y consecutivas
            'random': 16,        # KB - lecturas pequeñas y dispersas
            'mixed': 512         # KB - balance intermedio
        }
        
        row = {
            'run_id': run_id,
            'pattern': pattern,
            'cache_state': cache_state,
            'window_idx': idx,
            'time_start': round(w_start, 3),
            'time_end': round(w_end, 3),
            'target_readahead_kb': optimal_readahead.get(pattern, 256),
            **window_features
        }
        
        features_list.append(row)
    
    return features_list


def load_fio_metrics(run_dir):
    """Carga métricas globales de FIO desde los archivos JSON"""
    json_file = run_dir / "fio_output.json"
    
    if not json_file.exists():
        return {}
    
    try:
        with open(json_file) as f:
            data = json.load(f)
        
        job = data['jobs'][0]
        read_data = job.get('read', {})
        
        metrics = {
            'fio_iops': read_data.get('iops', 0),
            'fio_bw_kbps': read_data.get('bw', 0),
            'fio_lat_mean_us': read_data.get('lat', {}).get('mean', 0),
            'fio_lat_stddev_us': read_data.get('lat', {}).get('stddev', 0),
            'fio_slat_mean_us': read_data.get('slat', {}).get('mean', 0),
            'fio_clat_mean_us': read_data.get('clat', {}).get('mean', 0),
        }
        
        return metrics
    
    except Exception as e:
        print(f"  ⚠ Error cargando FIO metrics: {e}")
        return {}


def process_single_run(args):
    """Procesa un único run - diseñado para paralelización"""
    run_dir, pattern = args
    run_id = run_dir.name
    cache_state = 'cold' if 'cold' in run_id else 'warm'
    
    trace_file = run_dir / "trace.txt"
    
    if not trace_file.exists():
        return []
    
    print(f"  → Procesando {pattern}/{run_id} ({trace_file.stat().st_size / (1024**2):.1f} MB)")
    
    # Parsear eventos
    events = parse_trace_file(trace_file)
    
    if not events:
        print(f"    ⚠ Sin eventos extraídos")
        return []
    
    print(f"    ✓ {len(events):,} eventos extraídos")
    
    # Extraer features
    features = extract_features(events, pattern, run_id, cache_state)
    
    if not features:
        print(f"    ⚠ Sin features generadas")
        return []
    
    print(f"    ✓ {len(features):,} ventanas con features")
    
    # Cargar métricas FIO
    fio_metrics = load_fio_metrics(run_dir)
    
    # Enriquecer features con métricas FIO
    for f in features:
        f.update(fio_metrics)
    
    return features


# ============================================================================
# CONSOLIDACIÓN PRINCIPAL
# ============================================================================

def consolidate_dataset():
    """Función principal de consolidación"""
    print("=" * 80)
    print("CONSOLIDACIÓN AVANZADA DE DATASET MULTI-RUN")
    print("=" * 80)
    print(f"Directorio de trazas: {TRACES_DIR}")
    print(f"Ventana de análisis: {WINDOW_SIZE}s")
    print(f"Mínimo eventos por ventana: {MIN_EVENTS_PER_WINDOW}")
    print("=" * 80)
    
    all_rows = []
    patterns = ['sequential', 'random', 'mixed']
    
    # Recolectar todos los runs a procesar
    runs_to_process = []
    
    for pattern in patterns:
        pattern_dir = TRACES_DIR / pattern
        
        if not pattern_dir.exists():
            print(f"⚠ Patrón {pattern} no encontrado, saltando...")
            continue
        
        runs = sorted([r for r in pattern_dir.iterdir() if r.is_dir()])
        
        print(f"\n{'='*80}")
        print(f"Patrón: {pattern.upper()} ({len(runs)} runs)")
        print(f"{'='*80}")
        
        for run_dir in runs:
            runs_to_process.append((run_dir, pattern))
    
    if not runs_to_process:
        print("\n⚠ No se encontraron runs para procesar!")
        return
    
    print(f"\nTotal de runs a procesar: {len(runs_to_process)}")
    print("\nIniciando procesamiento paralelo...\n")
    
    # Procesamiento paralelo (usa todos los cores disponibles)
    num_workers = max(1, mp.cpu_count() - 1)
    print(f"Usando {num_workers} workers paralelos\n")
    
    with mp.Pool(num_workers) as pool:
        results = pool.map(process_single_run, runs_to_process)
    
    # Consolidar resultados
    for result in results:
        all_rows.extend(result)
    
    # ------------------------------------------------------------------------
    # Guardar CSV
    # ------------------------------------------------------------------------
    if not all_rows:
        print("\n⚠ No se generaron features. Verifica las trazas.")
        return
    
    print("\n" + "="*80)
    print("GUARDANDO DATASET")
    print("="*80)
    
    fieldnames = [
        'run_id', 'pattern', 'cache_state', 'window_idx',
        'time_start', 'time_end',
        'num_transactions', 'mean_offset', 'std_offset',
        'min_offset', 'max_offset', 'offset_range',
        'mean_abs_diff', 'std_abs_diff', 'max_abs_diff', 'min_abs_diff', 'median_abs_diff',
        'sequentiality',
        'count_block_io', 'count_page_add', 'count_syscall',
        'ratio_block_io', 'ratio_page_add',
        'fio_iops', 'fio_bw_kbps', 'fio_lat_mean_us', 'fio_lat_stddev_us',
        'fio_slat_mean_us', 'fio_clat_mean_us',
        'target_readahead_kb'
    ]
    
    with open(OUTPUT_FILE, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(all_rows)
    
    # ------------------------------------------------------------------------
    # Estadísticas
    # ------------------------------------------------------------------------
    total = len(all_rows)
    file_size_mb = OUTPUT_FILE.stat().st_size / (1024**2)
    
    print(f"\n✓ Dataset consolidado exitosamente!")
    print(f"  Total de muestras: {total:,}")
    print(f"  Tamaño archivo: {file_size_mb:.2f} MB")
    print(f"\nDistribución por patrón:")
    
    dist = defaultdict(int)
    for r in all_rows:
        dist[r['pattern']] += 1
    
    for p in sorted(dist.keys()):
        count = dist[p]
        pct = count / total * 100
        print(f"  {p:12s}: {count:8,} ({pct:5.1f}%)")
    
    print(f"\n✓ Archivo guardado: {OUTPUT_FILE}")
    print("="*80)


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    try:
        consolidate_dataset()
    except KeyboardInterrupt:
        print("\n\n⚠ Proceso interrumpido por el usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
