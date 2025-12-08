# Reporte de Análisis - Baseline VM

## Resumen Ejecutivo
- **Mayor throughput de lectura**: 307.2 MB/s en SEQ 500M
- **Mejor latencia p99**: 0.624 ms en SEQ 1G

## Métricas por Patrón de Acceso (Lectura)

### SEQ
- **100M**: 289.6 ± 1.9 MB/s, p99=0.629 ms
- **500M**: 307.2 ± 16.8 MB/s, p99=0.662 ms
- **1G**: 290.0 ± 1.2 MB/s, p99=0.624 ms

### RAND
- **100M**: 186.3 ± 3.0 MB/s, p99=0.894 ms
- **500M**: 183.3 ± 6.9 MB/s, p99=0.927 ms
- **1G**: 179.0 ± 2.6 MB/s, p99=0.930 ms

### MIX
- **100M**: 93.3 ± 8.1 MB/s, p99=1.264 ms
- **500M**: 97.3 ± 3.3 MB/s, p99=1.062 ms
- **1G**: 76.7 ± 21.0 MB/s, p99=4.762 ms

## Archivos Generados
- `resultados_detalle.csv`: métricas por corrida
- `resumen_metricas.csv`: agregados por patrón/tamaño
- `throughput_lectura.png`: gráfico de throughput
- `latencia_p99.png`: gráfico de latencia