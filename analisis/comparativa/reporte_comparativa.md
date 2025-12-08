# Análisis Comparativo: Baseline (VM) vs ML (Red Neuronal)

## Resumen Ejecutivo
- **Throughput promedio lectura**: Baseline 189.2 MB/s vs ML 230.5 MB/s (+21.9%)
- **Ganador general**: **ML**

## Comparativa por Patrón y Tamaño (Lectura)

### SEQ
- **100M**: 289.6 → 364.1 MB/s (+25.7%) [ML ✓]
- **500M**: 307.2 → 439.4 MB/s (+43.1%) [ML ✓]
- **1G**: 290.0 → 409.7 MB/s (+41.3%) [ML ✓]

### RAND
- **100M**: 186.3 → 189.2 MB/s (+1.6%) [ML ✓]
- **500M**: 183.3 → 215.9 MB/s (+17.8%) [ML ✓]
- **1G**: 179.0 → 197.4 MB/s (+10.3%) [ML ✓]

### MIX
- **100M**: 93.3 → 116.5 MB/s (+24.8%) [ML ✓]
- **500M**: 97.3 → 67.6 MB/s (-30.4%) [Baseline ✓]
- **1G**: 76.7 → 74.9 MB/s (-2.3%) [Baseline ✓]

## Observaciones
- Gráfico `comparativa_metricas.png` muestra comparación lado a lado
- CSV `comparativa_metricas.csv` contiene datos agregados detallados