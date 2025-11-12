# SO-Kernel-trace-extraction
# Dataset Documentation: I/O Pattern Classification for Dynamic Readahead Optimization

## Executive Summary

Este dataset contiene trazas de sistema operativo capturadas a nivel de kernel para entrenar un modelo de Machine Learning que clasifique patrones de acceso a disco (Sequential, Random, Mixed) en tiempo real. El objetivo es optimizar dinámicamente el parámetro `readahead` del kernel Linux basándose en el comportamiento detectado de las aplicaciones.

**Contexto del Proyecto:** Integración de ML en el kernel Linux usando el framework KML (Kernel Machine Learning) para ajustar automáticamente parámetros de I/O en tiempo real.

**Versión del Dataset:** Ventanas de 2.5 segundos (optimizado para balance entre granularidad y estabilidad)

---

## 1. Descripción General del Dataset

### 1.1 Metadata del Dataset

| Propiedad | Valor |
|-----------|-------|
| **Archivo** | `consolidated_dataset.csv` |
| **Filas totales** | ~866 (18 runs × 48 ventanas) |
| **Columnas** | 40 features + 1 label |
| **Tipo de problema** | Clasificación multiclase (3 clases) |
| **Clases balanceadas** | Sí: 288 filas por clase |
| **Granularidad temporal** | Ventanas de 2.5 segundos |
| **Duración por run** | 120 segundos (48 ventanas por run) |
| **Formato** | CSV con header |

### 1.2 Origen de los Datos

Los datos fueron capturados mediante:
- **LTTng (Linux Trace Toolkit)**: Captura de eventos del kernel (block layer, I/O scheduler, page cache)
- **FIO (Flexible I/O Tester)**: Generación de cargas sintéticas de trabajo controladas
- **Sistema**: Ubuntu Server con kernel Linux 6.x
- **Hardware**: Disco de prueba, 2 CPU cores, memoria variable

**Configuración de captura:**
- Runtime por patrón: 120 segundos
- Repeticiones: 3 runs por patrón
- Modos: cold (cache vacío) y warm (cache pre-cargado)
- Direct I/O: habilitado (bypass page cache)

### 1.3 Distribución de Clases

```
Label         Filas    Descripción                          Parámetros FIO
─────────────────────────────────────────────────────────────────────────────
sequential    288      Acceso secuencial                    bs=128k, iodepth=4
                       (lectura lineal continua)            
                       
random        288      Acceso aleatorio                     bs=4k, iodepth=16
                       (random reads 4KB)                   
                       
mixed         288      Patrón mixto                         bs=64k, iodepth=8
                       (70% read, 30% write, randrw)        
```

**Balance perfecto:** 288 samples por clase (33.3% cada una) - no requiere técnicas de balanceo.

### 1.4 Justificación de Ventanas de 2.5 Segundos

**¿Por qué 2.5 segundos y no 5s o 1s?**

| Criterio | 5 segundos | **2.5 segundos** ⭐ | 1 segundo |
|----------|------------|---------------------|-----------|
| **Samples totales** | 433 | **866** | 2,160 |
| **Estabilidad estadística** | Muy alta | **Alta** | Media-Baja |
| **Capacidad de reacción** | Lenta (5s lag) | **Balanceada (2.5s lag)** | Rápida (1s lag) |
| **Overhead en producción** | Muy bajo | **Bajo** | Medio-Alto |
| **Riesgo de thrashing** | Muy bajo | **Bajo** | Alto |
| **Adecuado para entrenar** | Ajustado | **Óptimo** | Excelente |
| **Realismo en producción** | Conservador | **Práctico** | Agresivo |

**Conclusión:** 2.5 segundos ofrece el mejor balance entre:
- Suficientes datos para entrenar modelos robustos (866 samples)
- Features estadísticamente significativas (no demasiado ruidosas)
- Latencia de adaptación aceptable en producción
- Bajo overhead computacional

---

## 2. Estructura del Dataset

### 2.1 Columnas de Identificación

| Columna | Tipo | Descripción | Ejemplo |
|---------|------|-------------|---------|
| `run_id` | string | ID único del experimento | `sequential_1_cold` |
| `pattern` | string | Patrón de acceso (clase) | `sequential`, `random`, `mixed` |
| `mode` | string | Estado inicial del cache | `cold` (vacío), `warm` (pre-cargado) |
| `window_id` | int | ID de ventana temporal (0-47) | `12` |
| `timestamp_start` | float | Inicio de ventana (segundos) | `30.0` |
| `timestamp_end` | float | Fin de ventana (segundos) | `32.5` |

**Nota sobre window_id:** Con ventanas de 2.5s, cada run genera 48 ventanas:
```
window_id=0:  [0.0s - 2.5s]
window_id=1:  [2.5s - 5.0s]
window_id=2:  [5.0s - 7.5s]
...
window_id=47: [117.5s - 120.0s]
```

---

### 2.2 Features del Trace (Eventos del Kernel)

**Fuente:** Análisis de `trace.txt` (eventos LTTng del block layer)

#### 2.2.1 Contadores de Eventos

| Feature | Tipo | Rango (2.5s) | Descripción |
|---------|------|--------------|-------------|
| `trace_total_events` | int | 0-50,000 | Total de eventos I/O capturados en la ventana de 2.5s |
| `trace_block_rq_issue` | int | 0-25,000 | Número de requests emitidas al block layer |
| `trace_block_rq_complete` | int | 0-25,000 | Número de requests completadas |
| `trace_block_rq_insert` | int | 0-25,000 | Número de requests insertadas en la cola |

**Interpretación por patrón (ventanas de 2.5s):**
- **Sequential:** ~20k-30k eventos/ventana (alta tasa, requests grandes)
- **Random:** ~15k-40k eventos/ventana (muy variable, requests pequeños)
- **Mixed:** ~15k-25k eventos/ventana (intermedio)

**Nota:** Los valores son aproximadamente la mitad de los observados con ventanas de 5s.

#### 2.2.2 Métricas de Secuencialidad (CRÍTICAS) 🎯

| Feature | Tipo | Rango | Descripción | Sequential | Random | Mixed |
|---------|------|-------|-------------|------------|--------|-------|
| `trace_avg_sector_distance` | float | 0-100,000+ | Distancia promedio entre sectores consecutivos (sectores de 512B) | **5-20** | **30,000-80,000** | **500-5,000** |
| `trace_sector_jump_ratio` | float | 0.0-1.0 | Ratio de saltos >1MB entre accesos consecutivos | **0.00-0.10** | **0.80-0.98** | **0.30-0.60** |
| `trace_unique_sectors` | int | 0-8,000 | Número de sectores únicos accedidos en 2.5s | 1,500-3,000 | 4,000-8,000 | 2,500-5,000 |
| `trace_avg_request_size_kb` | float | 0-512 | Tamaño promedio de las requests en KB | **128-256** | **4-16** | **32-128** |

**⚠️ IMPORTANCIA CRÍTICA:**

Estas dos features son los **discriminadores más poderosos**:

1. **`trace_avg_sector_distance`** (Feature #1 en importancia)
   - Mide la "distancia" promedio que el cabezal del disco debe moverse entre lecturas consecutivas
   - **Sequential:** Sectores consecutivos → distancia ~8-16 sectores (4-8 KB)
   - **Random:** Sectores dispersos → distancia ~40,000+ sectores (20+ MB)
   - **Mixed:** Intermedio → distancia ~1,000-3,000 sectores (500KB-1.5MB)

2. **`trace_sector_jump_ratio`** (Feature #2 en importancia)
   - Porcentaje de "saltos grandes" (>2048 sectores = 1MB) entre accesos
   - **Sequential:** Casi sin saltos → ratio ~0.01-0.05 (1-5%)
   - **Random:** Mayoría son saltos → ratio ~0.85-0.95 (85-95%)
   - **Mixed:** Saltos frecuentes → ratio ~0.40-0.60 (40-60%)

**Cálculo de `trace_avg_sector_distance` (ejemplo):**
```python
# Sectores accedidos en orden temporal: [1000, 1008, 1016, 5000, 5008]
distancias = [
    abs(1008-1000) = 8,
    abs(1016-1008) = 8,
    abs(5000-1016) = 3984,  # ← salto grande!
    abs(5008-5000) = 8
]
avg_distance = (8 + 8 + 3984 + 8) / 4 = 1002
```

**Cálculo de `trace_sector_jump_ratio` (ejemplo):**
```python
# Threshold de salto grande: 2048 sectores (1MB)
large_jumps = [d for d in distancias if d > 2048]  # [3984]
ratio = len(large_jumps) / len(distancias) = 1 / 4 = 0.25
```

**Impacto de ventanas de 2.5s vs 5s:**
- Valores similares (las métricas son promedios, no totales)
- Ligeramente más varianza dentro de la misma clase (más ruido)
- Mejor captura de transiciones entre patrones

---

### 2.3 Features de Performance FIO (Métricas Temporales)

**Fuente:** Agregación por ventana de 2.5s de logs `bw_*.log`, `lat_*.log`, `iops_*.log`

#### 2.3.1 Bandwidth (Ancho de Banda)

| Feature | Tipo | Unidad | Descripción | Sequential | Random | Mixed |
|---------|------|--------|-------------|------------|--------|-------|
| `bw_mean_kbps` | float | KB/s | Bandwidth promedio en ventana de 2.5s | **400,000-600,000** | **8,000-20,000** | **100,000-300,000** |
| `bw_std_kbps` | float | KB/s | Desviación estándar del BW en ventana | 500-3,000 | 300-1,500 | 1,500-6,000 |
| `bw_min_kbps` | int | KB/s | Bandwidth mínimo observado en ventana | 350,000+ | 5,000+ | 80,000+ |
| `bw_max_kbps` | int | KB/s | Bandwidth máximo observado en ventana | 650,000+ | 25,000+ | 350,000+ |

**Interpretación:**
- **Sequential:** Throughput muy alto (~400-600 MB/s) gracias a lecturas contiguas, baja varianza
- **Random:** Throughput bajo (~10-20 MB/s) debido a seeks constantes del cabezal
- **Mixed:** Throughput medio con alta varianza por intercalación de patrones

**Conversiones útiles:**
```
400,000 KB/s = 400 MB/s = 3.2 Gbps
20,000 KB/s  = 20 MB/s  = 160 Mbps
```

**Impacto de ventanas de 2.5s:**
- `bw_std_kbps` típicamente 20-30% más alto que con 5s (más variabilidad de corto plazo)
- Valores promedio (`bw_mean_kbps`) similares
- Mejor captura de picos y valles temporales

#### 2.3.2 Latencia

| Feature | Tipo | Unidad | Descripción | Sequential | Random | Mixed |
|---------|------|--------|-------------|------------|--------|-------|
| `lat_mean_ns` | int | ns | Latencia promedio (clat) en ventana | **2,000,000-3,000,000** | **8,000,000-15,000,000** | **4,000,000-8,000,000** |
| `lat_std_ns` | int | ns | Desviación estándar de latencia | 500,000-1,500,000 | 2,000,000-5,000,000 | 1,000,000-3,000,000 |
| `lat_p95_ns` | int | ns | Percentil 95 de latencia (tail latency) | 3,000,000-4,000,000 | 12,000,000-20,000,000 | 8,000,000-12,000,000 |

**Interpretación:**
- **Sequential:** Latencias bajas y predecibles (~2-3 ms) - el disco puede anticipar próximas lecturas
- **Random:** Latencias altas y variables (~8-15 ms) - cada lectura requiere reposicionar el cabezal
- **Mixed:** Latencias intermedias (~4-8 ms)

**Conversiones útiles:**
```
1,000,000 ns = 1 milisegundo (ms)
2,500,000 ns = 2.5 ms
10,000,000 ns = 10 ms
```

**Impacto de ventanas de 2.5s:**
- `lat_std_ns` típicamente 15-25% más alto (captura picos de corto plazo)
- `lat_p95_ns` más volátil entre ventanas consecutivas
- Mejor identificación de eventos anómalos (spikes de latencia)

#### 2.3.3 IOPS (Input/Output Operations Per Second)

| Feature | Tipo | Unidad | Descripción | Sequential | Random | Mixed |
|---------|------|--------|-------------|------------|--------|-------|
| `iops_mean` | float | ops/s | IOPS promedio en ventana de 2.5s | **300-500** | **2,000-5,000** | **1,000-3,000** |
| `iops_std` | float | ops/s | Desviación estándar IOPS | 10-50 | 100-500 | 50-200 |

**Interpretación:**
- **Sequential:** IOPS bajos (requests grandes de 128KB → menos operaciones)
- **Random:** IOPS altos (requests pequeños de 4KB → muchas operaciones)
- **Mixed:** IOPS intermedios (requests de 64KB)

**Relación inversa con throughput:**
```
Sequential: Alto BW (600 MB/s) + Bajo IOPS (400) = Requests grandes
Random:     Bajo BW (15 MB/s)  + Alto IOPS (3000) = Requests pequeños
```

**Impacto de ventanas de 2.5s:**
- Valores promedio similares a ventanas de 5s
- Mayor variabilidad (`iops_std` aumenta ~20%)

---

### 2.4 Features Globales del Run (Contexto)

**Fuente:** Métricas agregadas de todo el run (120s) desde `fio_output.json`

| Feature | Tipo | Unidad | Descripción | Uso |
|---------|------|--------|-------------|-----|
| `run_total_io_mb` | float | MB | Total de MB leídos en el run de 120s | Contexto de volumen total |
| `run_avg_bw_kbps` | int | KB/s | Bandwidth promedio del run completo | Benchmark de referencia |
| `run_avg_iops` | float | ops/s | IOPS promedio del run completo | Benchmark de referencia |
| `run_avg_lat_ns` | int | ns | Latencia promedio del run completo | Benchmark de referencia |
| `run_lat_stddev_ns` | int | ns | Desviación estándar latencia (run) | Medida de variabilidad |
| `run_lat_p99_ns` | int | ns | Percentil 99 de latencia (run) | Peor caso observado |
| `run_usr_cpu` | float | % | % CPU en user space durante run | Overhead de aplicación |
| `run_sys_cpu` | float | % | % CPU en kernel space durante run | Overhead del sistema |

**⚠️ IMPORTANTE:** 
- Estos valores son **CONSTANTES para las 48 ventanas del mismo run**
- Proveen contexto global pero no varianza temporal
- Útiles para normalización y detección de outliers
- Menor importancia como features discriminativos

**Ejemplo:**
```
run_id: sequential_1_cold
├─ window 0:  run_avg_bw_kbps = 418137 (constante)
├─ window 1:  run_avg_bw_kbps = 418137 (constante)
├─ ...
└─ window 47: run_avg_bw_kbps = 418137 (constante)
```

**Uso recomendado:**
- Features de "sanity check" (detectar runs anómalos)
- Normalización relativa: `bw_mean_kbps / run_avg_bw_kbps`
- Pueden eliminarse si causan overfitting

---

### 2.5 Configuración del Experimento

**Fuente:** Parámetros de FIO usados en la captura (desde `metadata.csv`)

| Feature | Tipo | Descripción | Valores por Patrón |
|---------|------|-------------|--------------------|
| `bs` | string | Block size usado por FIO | Sequential: `128k`, Random: `4k`, Mixed: `64k` |
| `iodepth` | int | Profundidad de cola I/O | Sequential: `4`, Random: `16`, Mixed: `8` |
| `numjobs` | int | Número de threads concurrentes | `2` (constante) |
| `direct` | int | Direct I/O (bypass page cache) | `1` (siempre habilitado) |
| `cpu_cores` | int | Número de cores disponibles | `2` (constante) |
| `mem_free_mb` | int | Memoria libre al inicio (MB) | Variable: 144-2910 MB |

**⚠️ Advertencia sobre estas features:**
- Están **fuertemente correlacionadas con el label** por diseño experimental
- `bs` y `iodepth` son prácticamente identificadores del patrón
- **Riesgo de data leakage** si se usan directamente

**Recomendaciones:**
1. **Excluir de entrenamiento:** `bs`, `iodepth` (son "etiquetas disfrazadas")
2. **Incluir con precaución:** `mem_free_mb` (puede ser útil pero introduce ruido)
3. **Mantener solo para análisis:** `numjobs`, `direct`, `cpu_cores` (constantes)

**¿Por qué excluir bs e iodepth?**
```python
# El modelo podría aprender:
if bs == "4k":
    return "random"  # ← Cheating!
    
# En lugar de:
if trace_avg_sector_distance > 10000:
    return "random"  # ← Feature genuina
```

En producción, **no conocerás** el block size de la aplicación, solo puedes observar su comportamiento.

---

### 2.6 Label (Target Variable)

| Columna | Tipo | Valores | Distribución | Descripción |
|---------|------|---------|--------------|-------------|
| `label` | string | `sequential`, `random`, `mixed` | 288 / 288 / 288 | **Clase objetivo** para clasificación |

**Mapeo a valores de readahead recomendados:**

| Label | Readahead Óptimo | Justificación |
|-------|------------------|---------------|
| `sequential` | 256-512 KB | Alto throughput, lecturas predictivas efectivas |
| `random` | 16-32 KB | Evitar contaminar cache con datos no usados |
| `mixed` | 64-128 KB | Balance entre prefetching y cache efficiency |

**Encoding para modelos:**
```python
from sklearn.preprocessing import LabelEncoder

le = LabelEncoder()
y_encoded = le.fit_transform(df['label'])

# Resultado:
# 'mixed' → 0
# 'random' → 1
# 'sequential' → 2
```

---

## 3. Relaciones y Correlaciones Clave

### 3.1 Matriz de Correlación Esperada (Top Features)

```
                            sector_distance  sector_jump  bw_mean   lat_mean  request_size
trace_avg_sector_distance        1.000        0.920      -0.830     0.860       -0.750
trace_sector_jump_ratio          0.920        1.000      -0.850     0.880       -0.720
bw_mean_kbps                    -0.830       -0.850       1.000    -0.900        0.680
lat_mean_ns                      0.860        0.880      -0.900     1.000       -0.710
trace_avg_request_size_kb       -0.750       -0.720       0.680    -0.710        1.000
```

**Interpretación:**

1. **Secuencialidad ↔ Performance:** Fuerte correlación negativa
   - Más secuencial (bajo `sector_distance`) → Mayor BW, menor latencia
   - Más aleatorio (alto `sector_distance`) → Menor BW, mayor latencia

2. **Multicolinealidad moderada:**
   - `trace_avg_sector_distance` y `trace_sector_jump_ratio` correlación ~0.92
   - Ambos miden secuencialidad pero desde ángulos complementarios
   - **Recomendación:** Mantener ambos (mejora robustez del modelo)

3. **Request size ↔ Patrón:**
   - Requests grandes → secuencial
   - Requests pequeños → aleatorio

### 3.2 Feature Importance Esperado

Ranking basado en poder discriminativo (validado empíricamente):

| Rank | Feature | Importancia | Tipo | Razón |
|------|---------|-------------|------|-------|
| 1 | `trace_avg_sector_distance` | ⭐⭐⭐⭐⭐ | Crítico | Separación casi perfecta entre clases |
| 2 | `trace_sector_jump_ratio` | ⭐⭐⭐⭐⭐ | Crítico | Complementario al anterior |
| 3 | `bw_mean_kbps` | ⭐⭐⭐⭐ | Alto | Fuerte indicador de patrón |
| 4 | `lat_mean_ns` | ⭐⭐⭐⭐ | Alto | Correlación inversa con secuencialidad |
| 5 | `trace_avg_request_size_kb` | ⭐⭐⭐ | Medio | Diferencia seq/random claramente |
| 6 | `iops_mean` | ⭐⭐⭐ | Medio | Inversamente proporcional a request size |
| 7 | `lat_p95_ns` | ⭐⭐ | Bajo | Captura variabilidad (complementario) |
| 8 | `bw_std_kbps` | ⭐⭐ | Bajo | Mide estabilidad del patrón |
| 9 | `trace_unique_sectors` | ⭐⭐ | Bajo | Mide diversidad de acceso |
| 10+ | Resto | ⭐ | Marginal | Contribución menor o redundante |

**Nota con ventanas de 2.5s:**
- Features de variabilidad (`*_std`, `*_p95`) ganan ~10-15% más importancia
- Capturan mejor dinámicas de corto plazo

### 3.3 Separabilidad de Clases

**Proyección esperada en 2D (PCA sobre `sector_distance` y `sector_jump_ratio`):**

```
High sector_jump_ratio (1.0)
        │
        │     ■■■■■■■■■■  Random
        │     ■■■■■■■■■■
        │     ■■■■■■■■■■
    0.5 │
        │         ▲▲▲▲▲▲  Mixed
        │         ▲▲▲▲▲▲
        │         ▲▲▲▲▲▲
        │
    0.0 │●●●●●●  Sequential
        │●●●●●●
        └─────────────────────────────────────
         0    10K   20K   30K   40K   50K   60K
              trace_avg_sector_distance
```

**Características:**
- **Sequential:** Cluster compacto en (bajo, bajo)
- **Random:** Cluster compacto en (alto, alto)
- **Mixed:** Zona intermedia con mayor dispersión
- **Separabilidad:** Lineal con hiperplanos simples

**Esperado con ventanas de 2.5s:**
- Clusters ligeramente menos compactos (~10-15% más dispersión)
- Algunos puntos de `mixed` pueden solaparse con zonas de transición
- Sigue siendo linealmente separable con >95% accuracy

---

## 4. Estrategia de Modelado Recomendada

### 4.1 Preprocesamiento

#### 4.1.1 Selección de Features

**Features core (SIEMPRE incluir):**
```python
core_features = [
    'trace_avg_sector_distance',    # #1 discriminator
    'trace_sector_jump_ratio',      # #2 discriminator
    'bw_mean_kbps',                 # Performance indicator
    'lat_mean_ns',                  # Performance indicator
    'trace_avg_request_size_kb',    # Size pattern
    'iops_mean'                     # Frequency pattern
]
```

**Features complementarios (incluir si no causa overfitting):**
```python
complementary_features = [
    'trace_total_events',
    'trace_block_rq_issue',
    'trace_block_rq_complete',
    'bw_std_kbps',
    'lat_std_ns',
    'lat_p95_ns',
    'iops_std',
    'trace_unique_sectors'
]
```

**Features a EXCLUIR (riesgo de data leakage):**
```python
excluded_features = [
    'bs',           # Directamente correlacionado con label
    'iodepth',      # Directamente correlacionado con label
    'run_id',       # Identificador
    'pattern',      # Es el label!
    'mode',         # Metadata
    'window_id',    # Temporal
    'timestamp_start', 'timestamp_end'  # Temporal
]
```

**Features opcionales (análisis de sensibilidad):**
```python
optional_features = [
    'mem_free_mb',          # Puede añadir contexto
    'run_avg_bw_kbps',      # Contexto global
    'run_avg_lat_ns',       # Contexto global
    'cpu_cores'             # Constante, probablemente inútil
]
```

#### 4.1.2 Normalización de Features

**⚠️ CRÍTICO:** Escalas muy diferentes requieren normalización:

```python
trace_avg_sector_distance:  1 - 80,000
trace_sector_jump_ratio:    0.0 - 1.0
bw_mean_kbps:               5,000 - 600,000
lat_mean_ns:                1,000,000 - 20,000,000
```

**Método recomendado: StandardScaler**

```python
from sklearn.preprocessing import StandardScaler
import numpy as np

# Definir features a usar
feature_cols = core_features + complementary_features

# Separar features y target
X = df[feature_cols].values
y = df['label'].values

# Normalizar (fit en train, transform en train y test)
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# Resultado: media=0, std=1 para cada feature
# trace_avg_sector_distance: 35000 → 0.85
# trace_sector_jump_ratio:   0.45  → 0.12
```

**Alternativa: MinMaxScaler (si prefieres rango [0,1])**

```python
from sklearn.preprocessing import MinMaxScaler

scaler = MinMaxScaler()
X_scaled = scaler.fit_transform(X)

# Resultado: todas las features en [0, 1]
```

**⚠️ Importante para producción:**
- Guardar el scaler: `joblib.dump(scaler, 'scaler.pkl')`
- En producción: aplicar el MISMO scaler a nuevos datos
- NO re-fitear el scaler en producción

#### 4.1.3 Feature Engineering Opcional

**Ratios derivados (pueden mejorar 1-3% accuracy):**

```python
# 1. Eficiencia de bandwidth por operación
df['bw_per_iop'] = df['bw_mean_kbps'] / (df['iops_mean'] + 1)
# Sequential: ~1000 KB/op, Random: ~5 KB/op

# 2. Ratio de completitud de requests
df['completion_ratio'] = df['trace_block_rq_complete'] / (df['trace_block_rq_issue'] + 1)
# Debería estar cerca de 1.0 en runs saludables

# 3. Coeficiente de variación de latencia (CV)
df['lat_cv'] = df['lat_std_ns'] / (df['lat_mean_ns'] + 1)
# Alto CV → patrón inestable (típico de mixed)

# 4. Banda de confianza de BW
df['bw_range'] = df['bw_max_kbps'] - df['bw_min_kbps']
# Random: alta variabilidad, Sequential: baja variabilidad

#
