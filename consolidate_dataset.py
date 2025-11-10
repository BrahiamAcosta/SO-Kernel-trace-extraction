#!/usr/bin/env python3
"""
Consolidador de Dataset para Entrenamiento de Modelo Readahead
Convierte trazas de LTTng a formato CSV con features y labels
"""

import re
import os
import csv
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import statistics

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

PROJECT_DIR = Path.home() / "kml-project"
TRACES_DIR = PROJECT_DIR / "traces" / "training"
OUTPUT_FILE = PROJECT_DIR / "traces" / "training_dataset.csv"

WINDOW_SIZE = 1.0  # Ventana temporal de 1 segundo (como en el paper)

# ============================================================================
# PARSING DE EVENTOS
# ============================================================================

def parse_timestamp(ts_str):
    """Convierte timestamp de LTTng a segundos flotantes"""
    # Formato: [HH:MM:SS.microseconds]
    match = re.match(r'\[(\d+):(\d+):(\d+)\.(\d+)\]', ts_str)
    if match:
        h, m, s, us = map(int, match.groups())
        return h * 3600 + m * 60 + s + us / 1_000_000
    return 0.0

def parse_trace_file(trace_file, pattern_label):
    """
    Parsea archivo de traza y extrae eventos relevantes
    """
    print(f"  Parseando: {trace_file.name}")
    
    events = []
    start_time = None
    
    with open(trace_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            # Formato LTTng: [timestamp] hostname event_name: { fields }
            
            # Extraer timestamp
            ts_match = re.match(r'\[(\d+:\d+:\d+\.\d+)\]', line)
            if not ts_match:
                continue
            
            timestamp = parse_timestamp(ts_match.group(1))
            if start_time is None:
                start_time = timestamp
            
            relative_time = timestamp - start_time
            
            # Eventos de interés
            event_data = {
                'time': relative_time,
                'pattern': pattern_label,
                'type': None,
                'inode': None,
                'offset': None,
                'size': None
            }
            
            # Page cache add
            if 'mm_filemap_add_to_page_cache' in line:
                event_data['type'] = 'page_add'
                
                # Extraer offset e inode
                offset_match = re.search(r'index = (\d+)', line)
                inode_match = re.search(r'i_ino = (\d+)', line)
                
                if offset_match:
                    event_data['offset'] = int(offset_match.group(1))
                if inode_match:
                    event_data['inode'] = int(inode_match.group(1))
            
            # Block requests
            elif 'block_rq_issue' in line or 'block_rq_insert' in line:
                event_data['type'] = 'block_io'
                
                sector_match = re.search(r'sector = (\d+)', line)
                size_match = re.search(r'nr_sector = (\d+)', line)
                
                if sector_match:
                    event_data['offset'] = int(sector_match.group(1))
                if size_match:
                    event_data['size'] = int(size_match.group(1))
            
            # Syscalls
            elif 'syscall_entry_read' in line or 'syscall_entry_pread64' in line:
                event_data['type'] = 'syscall_read'
                
                count_match = re.search(r'count = (\d+)', line)
                if count_match:
                    event_data['size'] = int(count_match.group(1))
            
            if event_data['type']:
                events.append(event_data)
            
            # Progress indicator
            if line_num % 100000 == 0:
                print(f"    Procesadas {line_num} líneas...")
    
    print(f"  ✓ Eventos extraídos: {len(events)}")
    return events

# ============================================================================
# EXTRACCIÓN DE FEATURES
# ============================================================================

def extract_features_windowed(events, window_size=1.0):
    """
    Extrae features por ventanas temporales
    
    Features (basado en paper KML):
    1. num_transactions: Número de transacciones por segundo
    2. mean_offset: Media móvil de offsets de página
    3. std_offset: Desviación estándar de offsets
    4. mean_abs_diff: Diferencia absoluta media entre offsets consecutivos
    5. current_readahead: Valor actual de readahead (simulado)
    """
    
    print(f"  Extrayendo features (ventanas de {window_size}s)...")
    
    if not events:
        return []
    
    features = []
    
    max_time = events[-1]['time']
    num_windows = int(max_time / window_size) + 1
    
    for window_idx in range(num_windows):
        window_start = window_idx * window_size
        window_end = window_start + window_size
        
        # Filtrar eventos en esta ventana
        window_events = [
            e for e in events 
            if window_start <= e['time'] < window_end and e['offset'] is not None
        ]
        
        if len(window_events) < 2:
            continue
        
        # Feature 1: Número de transacciones
        num_transactions = len(window_events)
        
        # Feature 2 y 3: Media y desviación estándar de offsets
        offsets = [e['offset'] for e in window_events]
        mean_offset = statistics.mean(offsets)
        std_offset = statistics.stdev(offsets) if len(offsets) > 1 else 0.0
        
        # Feature 4: Diferencia absoluta media entre offsets consecutivos
        offset_diffs = [abs(offsets[i+1] - offsets[i]) for i in range(len(offsets)-1)]
        mean_abs_diff = statistics.mean(offset_diffs) if offset_diffs else 0.0
        
        # Feature 5: Readahead actual (para entrenamiento, usar valor óptimo conocido)
        # Valores típicos del paper:
        optimal_readahead = {
            'sequential': 1024,  # sectores
            'random': 8,
            'mixed': 256
        }
        current_readahead = optimal_readahead.get(window_events[0]['pattern'], 256)
        
        feature_row = {
            'num_transactions': num_transactions,
            'mean_offset': mean_offset,
            'std_offset': std_offset,
            'mean_abs_diff': mean_abs_diff,
            'current_readahead': current_readahead,
            'label': window_events[0]['pattern']  # Etiqueta
        }
        
        features.append(feature_row)
    
    print(f"  ✓ Features extraídas: {len(features)} ventanas")
    return features

# ============================================================================
# CONSOLIDACIÓN
# ============================================================================

def consolidate_dataset():
    """
    Consolida todas las trazas en un único CSV
    """
    print("="*60)
    print("CONSOLIDACIÓN DE DATASET")
    print("="*60)
    print()
    
    all_features = []
    
    patterns = ['sequential', 'random', 'mixed']
    
    for pattern in patterns:
        print(f"Procesando patrón: {pattern.upper()}")
        
        trace_file = TRACES_DIR / pattern / "trace_events.txt"
        
        if not trace_file.exists():
            print(f"  ⚠ Archivo no encontrado: {trace_file}")
            continue
        
        # Parsear eventos
        events = parse_trace_file(trace_file, pattern)
        
        # Extraer features
        features = extract_features_windowed(events, WINDOW_SIZE)
        
        all_features.extend(features)
        print()
    
    # ========================================================================
    # GUARDAR CSV
    # ========================================================================
    
    print(f"Guardando dataset consolidado: {OUTPUT_FILE}")
    
    if not all_features:
        print("  ⚠ No hay features para guardar")
        return
    
    fieldnames = [
        'num_transactions',
        'mean_offset',
        'std_offset',
        'mean_abs_diff',
        'current_readahead',
        'label'
    ]
    
    with open(OUTPUT_FILE, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_features)
    
    print(f"  ✓ Archivo guardado: {OUTPUT_FILE}")
    print()
    
    # ========================================================================
    # ESTADÍSTICAS FINALES
    # ========================================================================
    
    print("="*60)
    print("ESTADÍSTICAS DEL DATASET")
    print("="*60)
    print()
    
    label_counts = defaultdict(int)
    for feat in all_features:
        label_counts[feat['label']] += 1
    
    total = len(all_features)
    
    print(f"Total de muestras: {total}")
    print()
    print("Distribución por clase:")
    for label in ['sequential', 'random', 'mixed']:
        count = label_counts[label]
        percent = (count / total * 100) if total > 0 else 0
        print(f"  {label:12s}: {count:6d} ({percent:5.1f}%)")
    
    print()
    print(f"Archivo de salida: {OUTPUT_FILE}")
    print(f"Tamaño: {OUTPUT_FILE.stat().st_size / 1024:.1f} KB")
    print()
    print("✓ Dataset listo para entrenamiento")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    consolidate_dataset()