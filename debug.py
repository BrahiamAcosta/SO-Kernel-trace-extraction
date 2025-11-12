#!/usr/bin/env python3
import re
from pathlib import Path

trace_file = Path("/root/kml-project/traces/training/sequential/run_1_cold/trace.txt")

print(f"Archivo: {trace_file}")
print(f"Existe: {trace_file.exists()}")

if not trace_file.exists():
    print("ERROR: Archivo no existe!")
    exit(1)

print(f"Tamaño: {trace_file.stat().st_size / (1024**2):.2f} MB\n")

events_found = 0
sectors_found = []

with open(trace_file, 'r', errors='ignore') as f:
    for i, line in enumerate(f):
        if i >= 100:
            break
        
        # Buscar eventos de interés
        if 'block_rq_issue' in line or 'block_rq_insert' in line or 'block_bio_queue' in line:
            # Extraer sector
            sector_match = re.search(r'sector\s*=\s*(\d+)', line)
            if sector_match:
                sector = int(sector_match.group(1))
                sectors_found.append(sector)
                events_found += 1
                if events_found <= 10:
                    print(f"Línea {i}: evento encontrado, sector = {sector}")

print(f"\n✓ Eventos encontrados en primeras 100 líneas: {events_found}")
if sectors_found:
    print(f"✓ Sectores: {sectors_found[:10]}")
    print(f"✓ El parser DEBERÍA funcionar")
else:
    print("✗ NO se encontraron sectores - problema con regex")
