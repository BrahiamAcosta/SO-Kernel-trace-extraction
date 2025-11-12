#!/usr/bin/env python3
"""
Consolidador de Trazas I/O para Entrenamiento de Modelo ML de Readahead
Genera un CSV con features por ventanas temporales de 5 segundos
"""

import os
import json
import pandas as pd
import numpy as np
from pathlib import Path
from collections import defaultdict
import re
from datetime import datetime

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

TRACES_DIR = Path.home() / "kml-project" / "traces" / "training"
OUTPUT_CSV = TRACES_DIR / "consolidated_dataset.csv"
WINDOW_SIZE_SECONDS = 5
METADATA_FILE = TRACES_DIR / "metadata.csv"

# ============================================================================
# FUNCIONES DE PARSING
# ============================================================================

def parse_trace_file(trace_path, window_size=5):
    """
    Parsea trace.txt y extrae features por ventanas temporales
    
    Returns:
        dict: {window_id: {features}}
    """
    if not trace_path.exists():
        print(f"  ⚠️  Archivo trace.txt no encontrado: {trace_path}")
        return {}
    
    print(f"  📄 Procesando trace.txt ({trace_path.stat().st_size / 1024 / 1024:.1f} MB)...")
    
    windows = defaultdict(lambda: {
        'total_events': 0,
        'block_rq_issue': 0,
        'block_rq_complete': 0,
        'block_rq_insert': 0,
        'sectors': [],
        'request_sizes': [],
        'timestamps': []
    })
    
    # Regex para parsear eventos
    event_pattern = re.compile(
        r'\[(\d+:\d+:\d+\.\d+)\].*?(\w+):\s*{.*?sector\s*=\s*(\d+).*?(?:bytes\s*=\s*(\d+)|size\s*=\s*(\d+))?'
    )
    
    first_timestamp = None
    
    try:
        with open(trace_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                match = event_pattern.search(line)
                if not match:
                    continue
                
                timestamp_str, event_type, sector, bytes1, bytes2 = match.groups()
                
                # Parsear timestamp (formato HH:MM:SS.microseconds)
                try:
                    h, m, s = timestamp_str.split(':')
                    total_seconds = int(h) * 3600 + int(m) * 60 + float(s)
                except:
                    continue
                
                if first_timestamp is None:
                    first_timestamp = total_seconds
                
                relative_time = total_seconds - first_timestamp
                window_id = int(relative_time // window_size)
                
                # Solo procesar ventanas dentro del runtime esperado (120s)
                if window_id >= 24:  # 120s / 5s = 24 ventanas
                    continue
                
                sector = int(sector)
                request_size = int(bytes1 or bytes2 or 0)
                
                windows[window_id]['total_events'] += 1
                windows[window_id]['timestamps'].append(relative_time)
                
                if event_type == 'block_rq_issue':
                    windows[window_id]['block_rq_issue'] += 1
                    windows[window_id]['sectors'].append(sector)
                    if request_size > 0:
                        windows[window_id]['request_sizes'].append(request_size)
                
                elif event_type == 'block_rq_complete':
                    windows[window_id]['block_rq_complete'] += 1
                
                elif event_type == 'block_rq_insert':
                    windows[window_id]['block_rq_insert'] += 1
    
    except Exception as e:
        print(f"  ⚠️  Error procesando trace: {e}")
        return {}
    
    # Calcular features por ventana
    features = {}
    for window_id, data in windows.items():
        sectors = data['sectors']
        request_sizes = data['request_sizes']
        
        # Calcular distancia promedio entre sectores consecutivos
        avg_sector_distance = 0
        sector_jump_ratio = 0
        
        if len(sectors) > 1:
            distances = [abs(sectors[i] - sectors[i-1]) for i in range(1, len(sectors))]
            avg_sector_distance = np.mean(distances) if distances else 0
            
            # Ratio de saltos grandes (>2048 sectores = 1MB para sectores de 512 bytes)
            large_jumps = sum(1 for d in distances if d > 2048)
            sector_jump_ratio = large_jumps / len(distances) if distances else 0
        
        features[window_id] = {
            'trace_total_events': data['total_events'],
            'trace_block_rq_issue': data['block_rq_issue'],
            'trace_block_rq_complete': data['block_rq_complete'],
            'trace_block_rq_insert': data['block_rq_insert'],
            'trace_avg_sector_distance': round(avg_sector_distance, 2),
            'trace_sector_jump_ratio': round(sector_jump_ratio, 4),
            'trace_unique_sectors': len(set(sectors)),
            'trace_avg_request_size_kb': round(np.mean(request_sizes) / 1024, 2) if request_sizes else 0
        }
    
    print(f"  ✓ Extraídas {len(features)} ventanas del trace")
    return features


def parse_fio_logs(run_dir, window_size=5):
    """
    Parsea los logs de FIO (bw, lat, iops) y agrupa por ventanas
    
    Returns:
        dict: {window_id: {bw_metrics, lat_metrics, iops_metrics}}
    """
    windows = defaultdict(lambda: {
        'bw_values': [],
        'lat_values': [],
        'iops_values': []
    })
    
    # Parsear bandwidth logs
    for bw_file in run_dir.glob("bw_bw.*.log"):
        try:
            with open(bw_file, 'r') as f:
                for line in f:
                    parts = line.strip().split(',')
                    if len(parts) >= 2:
                        timestamp_ms = int(parts[0].strip())
                        bw_kbps = int(parts[1].strip())
                        
                        window_id = int((timestamp_ms / 1000) // window_size)
                        if window_id < 24:
                            windows[window_id]['bw_values'].append(bw_kbps)
        except Exception as e:
            print(f"  ⚠️  Error en {bw_file.name}: {e}")
    
    # Parsear latency logs
    for lat_file in run_dir.glob("lat_clat.*.log"):
        try:
            with open(lat_file, 'r') as f:
                for line in f:
                    parts = line.strip().split(',')
                    if len(parts) >= 2:
                        timestamp_ms = int(parts[0].strip())
                        lat_ns = int(parts[1].strip())
                        
                        window_id = int((timestamp_ms / 1000) // window_size)
                        if window_id < 24:
                            windows[window_id]['lat_values'].append(lat_ns)
        except Exception as e:
            print(f"  ⚠️  Error en {lat_file.name}: {e}")
    
    # Parsear IOPS logs
    for iops_file in run_dir.glob("iops_iops.*.log"):
        try:
            with open(iops_file, 'r') as f:
                for line in f:
                    parts = line.strip().split(',')
                    if len(parts) >= 2:
                        timestamp_ms = int(parts[0].strip())
                        iops = int(parts[1].strip())
                        
                        window_id = int((timestamp_ms / 1000) // window_size)
                        if window_id < 24:
                            windows[window_id]['iops_values'].append(iops)
        except Exception as e:
            print(f"  ⚠️  Error en {iops_file.name}: {e}")
    
    # Calcular estadísticas por ventana
    features = {}
    for window_id, data in windows.items():
        bw_vals = data['bw_values']
        lat_vals = data['lat_values']
        iops_vals = data['iops_values']
        
        features[window_id] = {
            'bw_mean_kbps': round(np.mean(bw_vals), 2) if bw_vals else 0,
            'bw_std_kbps': round(np.std(bw_vals), 2) if bw_vals else 0,
            'bw_min_kbps': int(np.min(bw_vals)) if bw_vals else 0,
            'bw_max_kbps': int(np.max(bw_vals)) if bw_vals else 0,
            'lat_mean_ns': int(np.mean(lat_vals)) if lat_vals else 0,
            'lat_std_ns': int(np.std(lat_vals)) if lat_vals else 0,
            'lat_p95_ns': int(np.percentile(lat_vals, 95)) if lat_vals else 0,
            'iops_mean': round(np.mean(iops_vals), 2) if iops_vals else 0,
            'iops_std': round(np.std(iops_vals), 2) if iops_vals else 0
        }
    
    return features


def parse_fio_json(json_path):
    """
    Extrae métricas agregadas del run completo desde fio_output.json
    
    Returns:
        dict: métricas globales del run
    """
    if not json_path.exists():
        return {}
    
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        job = data['jobs'][0]
        read_stats = job['read']
        
        return {
            'run_total_io_mb': round(read_stats['io_bytes'] / (1024 * 1024), 2),
            'run_avg_bw_kbps': read_stats['bw'],
            'run_avg_iops': round(read_stats['iops'], 2),
            'run_avg_lat_ns': int(read_stats['clat_ns']['mean']),
            'run_lat_stddev_ns': int(read_stats['clat_ns']['stddev']),
            'run_lat_p99_ns': int(read_stats['clat_ns']['percentile']['99.000000']),
            'run_usr_cpu': round(job['usr_cpu'], 2),
            'run_sys_cpu': round(job['sys_cpu'], 2)
        }
    except Exception as e:
        print(f"  ⚠️  Error parseando fio_output.json: {e}")
        return {}


# ============================================================================
# CONSOLIDACIÓN PRINCIPAL
# ============================================================================

def consolidate_dataset():
    """
    Función principal que consolida todos los runs en un CSV
    """
    print("=" * 80)
    print("🚀 CONSOLIDADOR DE DATASET PARA ENTRENAMIENTO ML - READAHEAD")
    print("=" * 80)
    
    # Cargar metadata
    if not METADATA_FILE.exists():
        print(f"❌ No se encontró {METADATA_FILE}")
        return
    
    metadata_df = pd.read_csv(METADATA_FILE)
    print(f"\n✓ Metadata cargada: {len(metadata_df)} runs registrados")
    
    all_rows = []
    
    # Iterar por cada patrón
    for pattern in ['sequential', 'random', 'mixed']:
        pattern_dir = TRACES_DIR / pattern
        if not pattern_dir.exists():
            continue
        
        print(f"\n{'='*80}")
        print(f"📊 Procesando patrón: {pattern.upper()}")
        print(f"{'='*80}")
        
        # Iterar por cada run
        for run_dir in sorted(pattern_dir.glob("run_*")):
            run_name = run_dir.name
            print(f"\n🔍 {run_name}")
            
            # Extraer run_id y mode del nombre
            match = re.match(r'run_(\d+)_(cold|warm)', run_name)
            if not match:
                continue
            
            run_id = int(match.group(1))
            mode = match.group(2)
            
            # Buscar metadata correspondiente
            meta_row = metadata_df[
                (metadata_df['pattern'] == pattern) &
                (metadata_df['run_id'] == run_id) &
                (metadata_df['mode'] == mode)
            ]
            
            if meta_row.empty:
                print(f"  ⚠️  No se encontró metadata para este run")
                continue
            
            meta = meta_row.iloc[0].to_dict()
            
            # Parsear archivos
            trace_features = parse_trace_file(run_dir / "trace.txt", WINDOW_SIZE_SECONDS)
            fio_log_features = parse_fio_logs(run_dir, WINDOW_SIZE_SECONDS)
            fio_global = parse_fio_json(run_dir / "fio_output.json")
            
            # Determinar número de ventanas (mínimo entre trace y logs)
            if not trace_features and not fio_log_features:
                print(f"  ⚠️  No se pudieron extraer features")
                continue
            
            max_window = max(
                max(trace_features.keys()) if trace_features else 0,
                max(fio_log_features.keys()) if fio_log_features else 0
            )
            
            print(f"  ✓ Generando {max_window + 1} filas (ventanas de {WINDOW_SIZE_SECONDS}s)")
            
            # Crear una fila por ventana
            for window_id in range(max_window + 1):
                row = {
                    # Identificadores
                    'run_id': f"{pattern}_{run_id}_{mode}",
                    'pattern': pattern,
                    'mode': mode,
                    'window_id': window_id,
                    'timestamp_start': window_id * WINDOW_SIZE_SECONDS,
                    'timestamp_end': (window_id + 1) * WINDOW_SIZE_SECONDS,
                    
                    # Label
                    'label': pattern
                }
                
                # Features del trace
                trace_data = trace_features.get(window_id, {})
                row.update({
                    'trace_total_events': trace_data.get('trace_total_events', 0),
                    'trace_block_rq_issue': trace_data.get('trace_block_rq_issue', 0),
                    'trace_block_rq_complete': trace_data.get('trace_block_rq_complete', 0),
                    'trace_block_rq_insert': trace_data.get('trace_block_rq_insert', 0),
                    'trace_avg_sector_distance': trace_data.get('trace_avg_sector_distance', 0),
                    'trace_sector_jump_ratio': trace_data.get('trace_sector_jump_ratio', 0),
                    'trace_unique_sectors': trace_data.get('trace_unique_sectors', 0),
                    'trace_avg_request_size_kb': trace_data.get('trace_avg_request_size_kb', 0)
                })
                
                # Features de logs FIO
                log_data = fio_log_features.get(window_id, {})
                row.update({
                    'bw_mean_kbps': log_data.get('bw_mean_kbps', 0),
                    'bw_std_kbps': log_data.get('bw_std_kbps', 0),
                    'bw_min_kbps': log_data.get('bw_min_kbps', 0),
                    'bw_max_kbps': log_data.get('bw_max_kbps', 0),
                    'lat_mean_ns': log_data.get('lat_mean_ns', 0),
                    'lat_std_ns': log_data.get('lat_std_ns', 0),
                    'lat_p95_ns': log_data.get('lat_p95_ns', 0),
                    'iops_mean': log_data.get('iops_mean', 0),
                    'iops_std': log_data.get('iops_std', 0)
                })
                
                # Features globales del run (constantes por run)
                row.update(fio_global)
                
                # Configuración del experimento
                row.update({
                    'bs': meta.get('bs', ''),
                    'iodepth': meta.get('iodepth', 0),
                    'numjobs': meta.get('numjobs', 0),
                    'direct': meta.get('direct', 0),
                    'cpu_cores': meta.get('cpu_cores', 0),
                    'mem_free_mb': meta.get('mem_free_mb', 0)
                })
                
                all_rows.append(row)
    
    # Crear DataFrame y guardar
    if not all_rows:
        print("\n❌ No se generaron filas. Revisa los datos de entrada.")
        return
    
    df = pd.DataFrame(all_rows)
    
    # Reordenar columnas para mayor claridad
    column_order = [
        'run_id', 'pattern', 'mode', 'window_id', 'timestamp_start', 'timestamp_end',
        'trace_total_events', 'trace_block_rq_issue', 'trace_block_rq_complete', 
        'trace_block_rq_insert', 'trace_avg_sector_distance', 'trace_sector_jump_ratio',
        'trace_unique_sectors', 'trace_avg_request_size_kb',
        'bw_mean_kbps', 'bw_std_kbps', 'bw_min_kbps', 'bw_max_kbps',
        'lat_mean_ns', 'lat_std_ns', 'lat_p95_ns',
        'iops_mean', 'iops_std',
        'run_total_io_mb', 'run_avg_bw_kbps', 'run_avg_iops', 'run_avg_lat_ns',
        'run_lat_stddev_ns', 'run_lat_p99_ns', 'run_usr_cpu', 'run_sys_cpu',
        'bs', 'iodepth', 'numjobs', 'direct', 'cpu_cores', 'mem_free_mb',
        'label'
    ]
    
    # Solo incluir columnas que existen
    column_order = [col for col in column_order if col in df.columns]
    df = df[column_order]
    
    # Guardar CSV
    df.to_csv(OUTPUT_CSV, index=False)
    
    print(f"\n{'='*80}")
    print("✅ CONSOLIDACIÓN COMPLETADA")
    print(f"{'='*80}")
    print(f"📁 Archivo generado: {OUTPUT_CSV}")
    print(f"📊 Total de filas: {len(df)}")
    print(f"📈 Distribución por patrón:")
    print(df['pattern'].value_counts().to_string())
    print(f"\n🎯 Features generadas: {len(df.columns)}")
    print(f"🏷️  Label: 'label' → {df['label'].unique()}")
    
    # Estadísticas básicas
    print(f"\n📉 Estadísticas de features principales:")
    print(df[['trace_avg_sector_distance', 'trace_sector_jump_ratio', 
              'bw_mean_kbps', 'lat_mean_ns', 'iops_mean']].describe())


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    consolidate_dataset()
