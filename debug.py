#!/usr/bin/env python3
import re
from pathlib import Path

trace_file = Path.home() / "kml-project/traces/training/sequential/run_1_cold/trace.txt"

print(f"Archivo: {trace_file}")
print(f"Existe: {trace_file.exists()}")
print(f"Tamaño: {trace_file.stat().st_size / (1024**2):.2f} MB")

events_found = 0
with open(trace_file, 'r', errors='ignore') as f:
    for i, line in enumerate(f):
        if i >= 100:  # Solo primeras 100 líneas
            break
        
        # Buscar eventos block
        if 'block_rq_issue' in line or 'block_rq_insert' in line:
            # Extraer sector
            sector_match = re.search(r'sector\s*=\s*(\d+)', line)
            if sector_match:
                events_found += 1
                print(f"Línea {i}: sector = {sector_match.group(1)}")

print(f"\nEventos encontrados en primeras 100 líneas: {events_found}")
