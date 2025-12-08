# Análisis de Rendimiento FIO: Baseline VM vs ML

Análisis comparativo completo de experimentos de I/O usando FIO entre una línea base (VM) y una implementación basada en red neuronal.

## 📁 Estructura

```
analisis/
├── baseline/              # Análisis línea base (VM)
│   ├── throughput_lectura.png
│   ├── latencia_p99.png
│   ├── resultados_detalle.csv
│   ├── resumen_metricas.csv
│   └── reporte_baseline.md
├── ml/                    # Análisis Red Neuronal
│   ├── throughput_lectura.png
│   ├── latencia_p99.png
│   ├── resultados_detalle.csv
│   ├── resumen_metricas.csv
│   └── reporte_ml.md
├── comparativa/           # Análisis Comparativo
│   ├── comparativa_metricas.png
│   ├── resultados_combinados.csv
│   ├── comparativa_metricas.csv
│   └── reporte_comparativa.md
├── analizar.py           # Script principal
└── README.md             # Este archivo
```

## 🚀 Ejecución Rápida

```powershell
python analisis/analizar.py
```

El script ejecutará todo el pipeline automáticamente y generará:

- 2 gráficos por implementación (throughput + latencia)
- 1 gráfico comparativo side-by-side
- Reportes markdown con hallazgos
- Archivos CSV con datos detallados

## 📊 Gráficos Generados

### Baseline (VM)

- **throughput_lectura.png**: Throughput de lectura por patrón y tamaño
- **latencia_p99.png**: Latencia p99 de lectura

### ML (Red Neuronal)

- **throughput_lectura.png**: Throughput de lectura (ML)
- **latencia_p99.png**: Latencia p99 de lectura (ML)

### Comparativa

- **comparativa_metricas.png**: Throughput y latencia side-by-side (Baseline vs ML)

## 📈 Interpretación de Resultados

### Throughput (MB/s)

Mayor es mejor. Compara velocidad de lectura en diferentes patrones:

- **SEQ**: Acceso secuencial (mejor caso)
- **RAND**: Acceso aleatorio (peor caso)
- **MIX**: Acceso mixto

### Latencia p99 (ms)

Menor es mejor. Percentil 99 del tiempo de respuesta.

## 📄 Reportes Markdown

- `baseline/reporte_baseline.md`: Resumen de hallazgos Baseline
- `ml/reporte_ml.md`: Resumen de hallazgos ML
- `comparativa/reporte_comparativa.md`: Análisis comparativo detallado

## 📊 Archivos CSV

### Detalle

- `resultados_detalle.csv`: Métrica por corrida individual
- Columnas: workload, size_label, run, op, bw_MB_s, iops, p99_ms, lat_mean_ms

### Resumen

- `resumen_metricas.csv`: Agregados por patrón/tamaño/operación
- Columnas: workload, op, size_label, runs, bw_MB_s_mean, bw_MB_s_std, p99_ms_mean

### Comparativa

- `comparativa_metricas.csv`: Datos combinados con implementación
- `resultados_combinados.csv`: Detalle completo con etiqueta de implementación

## 🔧 Requisitos

```powershell
pip install pandas numpy matplotlib seaborn
```

## 📝 Hallazgos Clave

Los reportes markdown en cada carpeta contienen:

- Resumen ejecutivo con métricas principales
- Desglose por patrón de acceso (SEQ, RAND, MIX)
- Análisis comparativo con deltas porcentuales

## 🎯 Próximos Pasos

1. Revisar gráficos en cada carpeta
2. Leer reportes markdown para interpretación
3. Analizar CSV con herramientas adicionales si se requiere
4. Comparar resultados entre baseline y ML en carpeta `comparativa/`

## 🚀 Inicio Rápido

### Prerequisitos

Asegúrate de tener instaladas las siguientes librerías de Python:

```powershell
pip install pandas numpy matplotlib seaborn
```

O instala todas las dependencias desde el archivo de requisitos del proyecto:

```powershell
pip install -r ../requirements.txt
```

### Ejecución del Análisis Completo

Para ejecutar todo el pipeline de análisis de una vez:

```powershell
cd analisis
python run_analysis.py
```

Este comando ejecutará:

1. Procesamiento de todos los archivos JSON de resultados
2. Generación de estadísticas agregadas
3. Creación de todas las gráficas
4. Generación del reporte de hallazgos

## 📊 Ejecución Módulo por Módulo

Si prefieres ejecutar cada componente por separado:

### 1. Procesar Resultados

```powershell
python process_results.py
```

**Salidas generadas:**

- `processed_results.csv`: Dataset completo con todos los experimentos procesados
- `statistics_summary.csv`: Estadísticas agregadas por configuración

### 2. Generar Gráficas

```powershell
python generate_plots.py
```

**Gráficas generadas:**

- `iops_comparison.png`: Comparación de IOPS por tipo de acceso y tamaño
- `bandwidth_comparison.png`: Análisis de ancho de banda
- `latency_analysis.png`: Análisis detallado de latencia (4 subgráficas)
- `throughput_efficiency.png`: Eficiencia de throughput
- `performance_heatmap.png`: Mapas de calor de rendimiento (4 métricas)
- `comparative_radar.png`: Gráfica radar comparativa de rendimiento normalizado
- `variability_analysis.png`: Análisis de consistencia entre runs (4 subgráficas)
- `percentile_latency.png`: Percentiles de latencia (P50, P95, P99)

### 3. Generar Reporte

```powershell
python generate_report.py
```

**Salida generada:**

- `REPORTE_HALLAZGOS.md`: Reporte completo en formato Markdown con:
  - Resumen ejecutivo
  - Métricas principales
  - Análisis por tipo de acceso
  - Análisis de escalabilidad
  - Análisis de latencia
  - Análisis de variabilidad
  - Hallazgos clave
  - Recomendaciones
  - Conclusiones

## 📈 Estructura de Datos

### Datos de Entrada

Los scripts procesan los resultados ubicados en:

```
../experiments/results_baseline/
├── seq/
│   ├── 100M/
│   │   ├── result_100M_run1.json
│   │   ├── result_100M_run2.json
│   │   └── result_100M_run3.json
│   ├── 500M/
│   └── 1G/
├── rand/
│   ├── 100M/
│   ├── 500M/
│   └── 1G/
└── mix/
    ├── 100M/
    ├── 500M/
    └── 1G/
```

### Configuración de Experimentos

- **Patrones de acceso**: Secuencial (seq), Aleatorio (rand), Mixto (mix)
- **Tamaños de archivo**: 100M, 500M, 1G
- **Repeticiones**: 3 runs por configuración
- **Total de experimentos**: 27 ejecuciones (3 × 3 × 3)

### Métricas Analizadas

#### Principales

- **IOPS** (I/O Operations Per Second): Operaciones de entrada/salida por segundo
- **Ancho de Banda** (MB/s): Throughput en megabytes por segundo
- **Latencia** (μs): Tiempo de respuesta en microsegundos

#### Métricas Detalladas

- Latencia media, mínima, máxima y desviación estándar
- Percentiles de latencia (P50, P95, P99)
- Total de datos procesados
- Throughput efectivo
- Coeficiente de variación

## 🔍 Interpretación de Resultados

### IOPS (Input/Output Operations Per Second)

- **Mayor es mejor**
- Indica cuántas operaciones de I/O puede procesar el sistema por segundo
- Crítico para aplicaciones con muchas operaciones pequeñas

### Ancho de Banda (Bandwidth)

- **Mayor es mejor**
- Medido en MB/s
- Indica la cantidad de datos que pueden transferirse por unidad de tiempo
- Importante para operaciones con archivos grandes

### Latencia

- **Menor es mejor**
- Medida en microsegundos (μs)
- Tiempo que tarda en completarse una operación de I/O
- Los percentiles altos (P95, P99) son críticos para detectar outliers

### Coeficiente de Variación (CV)

- Mide la consistencia de los resultados entre ejecuciones
- **CV < 5%**: Excelente consistencia
- **CV 5-10%**: Buena consistencia
- **CV 10-15%**: Consistencia moderada
- **CV > 15%**: Alta variabilidad

## 📦 Archivos Generados

Después de ejecutar el análisis completo, encontrarás:

```
analisis/
├── process_results.py
├── generate_plots.py
├── generate_report.py
├── run_analysis.py
├── README.md
├── processed_results.csv           # Dataset procesado
├── statistics_summary.csv          # Estadísticas agregadas
├── REPORTE_HALLAZGOS.md           # Reporte de hallazgos
├── iops_comparison.png
├── bandwidth_comparison.png
├── latency_analysis.png
├── throughput_efficiency.png
├── performance_heatmap.png
├── comparative_radar.png
├── variability_analysis.png
└── percentile_latency.png
```

## 🛠️ Personalización

### Modificar Rutas

Si tus resultados están en una ubicación diferente, modifica la variable `results_path` en cada script:

```python
results_path = Path('ruta/a/tus/resultados')
```

### Agregar Nuevas Métricas

1. Edita `process_results.py` para extraer métricas adicionales del JSON
2. Actualiza `generate_plots.py` para visualizar las nuevas métricas
3. Modifica `generate_report.py` para incluirlas en el reporte

### Cambiar Estilo de Gráficas

En `generate_plots.py`, ajusta los parámetros de estilo:

```python
plt.style.use('seaborn-v0_8-darkgrid')  # Cambiar estilo
sns.set_palette("husl")                  # Cambiar paleta de colores
plt.rcParams['figure.figsize'] = (12, 8) # Ajustar tamaño
```

## 📊 Visualizaciones Disponibles

### 1. IOPS Comparison

- Barras agrupadas y box plots
- Compara IOPS entre patrones de acceso y tamaños

### 2. Bandwidth Comparison

- Barras y gráficas de línea
- Muestra tendencias de ancho de banda

### 3. Latency Analysis

- 4 subgráficas con análisis completo
- Incluye distribución, variabilidad y rangos

### 4. Throughput Efficiency

- Throughput efectivo y datos procesados
- Evalúa eficiencia del sistema

### 5. Performance Heatmap

- 4 mapas de calor
- Visualización rápida de patrones de rendimiento

### 6. Comparative Radar

- Gráfica tipo radar
- Compara rendimiento normalizado entre patrones

### 7. Variability Analysis

- 4 subgráficas sobre consistencia
- Evalúa variabilidad entre runs

### 8. Percentile Latency

- Percentiles P50, P95 y P99
- Identifica latencias extremas

## 🐛 Solución de Problemas

### Error: "No module named 'pandas'"

```powershell
pip install pandas numpy matplotlib seaborn
```

### Error: "File not found"

Verifica que los resultados estén en la ruta correcta:

```
../experiments/results_baseline/
```

### Gráficas no se generan

Asegúrate de haber ejecutado primero `process_results.py` o `run_analysis.py`

### Warnings sobre seaborn

Si ves warnings sobre estilos de seaborn, es normal. Las gráficas se generarán correctamente.

## 📝 Notas Adicionales

- Todos los scripts están diseñados para ejecutarse de forma independiente o conjunta
- Los resultados son reproducibles gracias al procesamiento determinístico
- Las gráficas se generan en alta resolución (300 DPI) para publicaciones
- El reporte está en formato Markdown, fácil de convertir a PDF o HTML

## 📞 Contacto y Soporte

Para preguntas o problemas relacionados con el análisis:

- Revisa el código fuente de los scripts (están bien comentados)
- Consulta el reporte de hallazgos generado
- Verifica que todos los prerequisitos estén instalados

## 🔄 Actualización de Análisis

Para actualizar el análisis con nuevos resultados:

1. Asegúrate de que los nuevos archivos JSON estén en la estructura correcta
2. Ejecuta nuevamente:
   ```powershell
   python run_analysis.py
   ```
3. Los archivos existentes serán sobrescritos con los nuevos resultados

## 📄 Licencia

Este código de análisis es parte del proyecto SO-Kernel-trace-extraction.

---

**Última actualización:** Diciembre 2025
