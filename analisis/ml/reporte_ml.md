# Reporte de Análisis - ML (Red Neuronal)

## Resumen Ejecutivo
- **Mayor throughput de lectura**: 439.4 MB/s en SEQ 500M
- **Mejor latencia p99**: 0.575 ms en SEQ 500M

## Métricas por Patrón de Acceso (Lectura)

### SEQ
- **100M**: 364.1 ± 2.2 MB/s, p99=1.128 ms
- **500M**: 439.4 ± 1.7 MB/s, p99=0.575 ms
- **1G**: 409.7 ± 3.8 MB/s, p99=0.990 ms

### RAND
- **100M**: 189.2 ± 0.6 MB/s, p99=1.647 ms
- **500M**: 215.9 ± 1.4 MB/s, p99=0.916 ms
- **1G**: 197.4 ± 0.9 MB/s, p99=1.461 ms

### MIX
- **100M**: 116.5 ± 8.4 MB/s, p99=1.290 ms
- **500M**: 67.6 ± 58.7 MB/s, p99=64.674 ms
- **1G**: 74.9 ± 19.0 MB/s, p99=8.645 ms

## Archivos Generados
- `resultados_detalle.csv`: métricas por corrida
- `resumen_metricas.csv`: agregados por patrón/tamaño
- `throughput_lectura.png`: gráfico de throughput
- `latencia_p99.png`: gráfico de latencia