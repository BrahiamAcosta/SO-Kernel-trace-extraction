#!/usr/bin/env python3
"""
Script de diagnóstico para analizar trazas LTTng
Identifica qué eventos están realmente presentes
"""

import re
from pathlib import Path
from collections import Counter

PROJECT_DIR = Path.home() / "kml-project"
TRACES_DIR = PROJECT_DIR / "traces" / "training"

def analyze_trace_file(trace_file, max_lines=10000):
    """Analiza un archivo de traza y muestra estadísticas"""
    print(f"\n{'='*80}")
    print(f"Analizando: {trace_file}")
    print(f"Tamaño: {trace_file.stat().st_size / (1024**2):.2f} MB")
    print(f"{'='*80}")
    
    event_types = Counter()
    sample_events = []
    total_lines = 0
    lines_with_timestamps = 0
    
    try:
        with open(trace_file, 'r', errors='ignore') as f:
            for i, line in enumerate(f):
                total_lines += 1
                
                # Verificar si tiene timestamp
                if re.search(r'\[\d+:\d+:\d+\.\d+\]', line):
                    lines_with_timestamps += 1
                    
                    # Guardar primeras 20 líneas como ejemplo
                    if len(sample_events) < 20:
                        sample_events.append(line.strip())
                    
                    # Extraer tipo de evento (texto después del timestamp)
                    match = re.search(r'\]\s+\w+:\s+(\S+):', line)
                    if match:
                        event_types[match.group(1)] += 1
                    else:
                        # Intentar otro formato
                        match = re.search(r'\]\s+(\S+):', line)
                        if match:
                            event_types[match.group(1)] += 1
                
                # Limitar análisis para archivos muy grandes
                if i >= max_lines and max_lines > 0:
                    print(f"(Análisis limitado a primeras {max_lines:,} líneas)")
                    break
        
        print(f"\n📊 Estadísticas:")
        print(f"  Total líneas: {total_lines:,}")
        print(f"  Líneas con timestamp: {lines_with_timestamps:,}")
        print(f"  Tipos de eventos únicos: {len(event_types)}")
        
        if event_types:
            print(f"\n🔝 Top 20 eventos más frecuentes:")
            for event, count in event_types.most_common(20):
                print(f"  {event:40s}: {count:8,}")
        
        if sample_events:
            print(f"\n📝 Primeras 20 líneas de ejemplo:")
            for i, line in enumerate(sample_events, 1):
                print(f"  {i:2d}. {line[:150]}")
                if len(line) > 150:
                    print(f"      ...")
        
        return event_types, lines_with_timestamps > 0
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return Counter(), False


def main():
    print("="*80)
    print("DIAGNÓSTICO DE TRAZAS LTTNG")
    print("="*80)
    
    patterns = ['sequential', 'random', 'mixed']
    
    for pattern in patterns:
        pattern_dir = TRACES_DIR / pattern
        
        if not pattern_dir.exists():
            print(f"\n⚠ Patrón {pattern} no encontrado")
            continue
        
        runs = sorted([r for r in pattern_dir.iterdir() if r.is_dir()])
        
        if not runs:
            print(f"\n⚠ No hay runs en {pattern}")
            continue
        
        print(f"\n\n{'#'*80}")
        print(f"# PATRÓN: {pattern.upper()}")
        print(f"# Runs encontrados: {len(runs)}")
        print(f"{'#'*80}")
        
        # Analizar solo el primer run de cada patrón como muestra
        for run_dir in runs[:2]:  # Primeros 2 runs
            trace_file = run_dir / "trace.txt"
            
            if not trace_file.exists():
                print(f"\n⚠ {run_dir.name}: trace.txt no existe")
                continue
            
            if trace_file.stat().st_size == 0:
                print(f"\n⚠ {run_dir.name}: trace.txt está vacío")
                continue
            
            analyze_trace_file(trace_file, max_lines=5000)
    
    print("\n" + "="*80)
    print("DIAGNÓSTICO COMPLETO")
    print("="*80)
    print("\n💡 Busca en la salida:")
    print("  1. Que las líneas tengan timestamps [HH:MM:SS.microsec]")
    print("  2. Que haya eventos relacionados con block/io/syscall")
    print("  3. Que los eventos tengan campos como 'sector' o 'index'")


if __name__ == "__main__":
    main()
