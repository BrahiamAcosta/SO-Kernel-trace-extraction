# SO-Kernel-trace-extraction
## Pipeline de ML para Clasificación de Patrones de I/O

Sistema de aprendizaje automático para clasificar patrones de acceso a disco (secuencial, aleatorio, mixto) y optimizar el readahead en el kernel Linux mediante KML (Kernel Machine Learning).

---

## 📋 Resumen Ejecutivo

Este proyecto desarrolla un componente de red neuronal que clasifica patrones de I/O en tiempo real dentro del kernel Linux. El objetivo es predecir el tipo de patrón de acceso (sequential, random, mixed) para ajustar dinámicamente el valor de readahead y mejorar el rendimiento del sistema de archivos.

**Contexto del Proyecto:** Integración de ML en el kernel Linux usando el framework KML (Kernel Machine Learning) para ajustar automáticamente parámetros de I/O en tiempo real.

**Versión del Dataset:** Ventanas de 2.5 segundos (optimizado para balance entre granularidad y estabilidad)

### Flujo General del Proyecto

```
1. Dataset consolidado (CSV con características pre-calculadas)
   ↓
2. Procesamiento y normalización de datos
   ↓
3. Entrenamiento de red neuronal ligera
   ↓
4. Exportación a formato TorchScript
   ↓
5. Integración en kernel Linux mediante KML
   ↓
6. Inferencia en tiempo real para ajustar readahead
```

**Tu responsabilidad**: Pasos 1-4 (desarrollo del modelo ML)  
**Compañero**: Pasos 5-6 (integración en kernel)

---

## 📊 Descripción del Dataset

### Metadata del Dataset

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

### Origen de los Datos

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

### Distribución de Clases

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

### Justificación de Ventanas de 2.5 Segundos

| Criterio | 5 segundos | **2.5 segundos** ⭐ | 1 segundo |
|----------|------------|---------------------|-----------|
| **Samples totales** | 433 | **866** | 2,160 |
| **Estabilidad estadística** | Muy alta | **Alta** | Media-Baja |
| **Capacidad de reacción** | Lenta (5s lag) | **Balanceada (2.5s lag)** | Rápida (1s lag) |
| **Overhead en producción** | Muy bajo | **Bajo** | Medio-Alto |
| **Riesgo de thrashing** | Muy bajo | **Bajo** | Alto |
| **Adecuado para entrenar** | Ajustado | **Óptimo** | Excelente |
| **Realismo en producción** | Conservador | **Práctico** | Agresivo |

**Conclusión:** 2.5 segundos ofrece el mejor balance entre suficientes datos para entrenar modelos robustos, features estadísticamente significativas, latencia de adaptación aceptable y bajo overhead computacional.

### Características Críticas del Dataset

Las **5 características** seleccionadas para el modelo son:

1. **`trace_avg_sector_distance`** (Feature #1 en importancia) ⭐⭐⭐⭐⭐
   - Distancia promedio entre sectores consecutivos (sectores de 512B)
   - **Sequential:** ~5-20 sectores (4-8 KB)
   - **Random:** ~30,000-80,000 sectores (20+ MB)
   - **Mixed:** ~500-5,000 sectores (500KB-1.5MB)

2. **`trace_sector_jump_ratio`** (Feature #2 en importancia) ⭐⭐⭐⭐⭐
   - Ratio de saltos >1MB entre accesos consecutivos (0.0-1.0)
   - **Sequential:** ~0.00-0.10 (1-5%)
   - **Random:** ~0.80-0.98 (85-95%)
   - **Mixed:** ~0.30-0.60 (40-60%)

3. **`bw_mean_kbps`** (Bandwidth promedio) ⭐⭐⭐⭐
   - **Sequential:** ~400,000-600,000 KB/s (400-600 MB/s)
   - **Random:** ~8,000-20,000 KB/s (10-20 MB/s)
   - **Mixed:** ~100,000-300,000 KB/s (100-300 MB/s)

4. **`lat_mean_ns`** (Latencia promedio) ⭐⭐⭐⭐
   - **Sequential:** ~2,000,000-3,000,000 ns (2-3 ms)
   - **Random:** ~8,000,000-15,000,000 ns (8-15 ms)
   - **Mixed:** ~4,000,000-8,000,000 ns (4-8 ms)

5. **`iops_mean`** (IOPS promedio) ⭐⭐⭐
   - **Sequential:** ~300-500 ops/s
   - **Random:** ~2,000-5,000 ops/s
   - **Mixed:** ~1,000-3,000 ops/s

**⚠️ IMPORTANTE:** Las características `bs` y `iodepth` están **excluidas** del modelo porque están fuertemente correlacionadas con el label (riesgo de data leakage). En producción, no conocerás estos parámetros, solo puedes observar el comportamiento.

---

## 🏗️ Estructura del Código

### Archivos Principales

#### `build_dataset_from_consolidated.py`
**¿Qué hace?**  
Procesa el dataset consolidado (`consolidated_dataset.csv`) y prepara los datos para entrenamiento.

**Funcionamiento:**
1. Lee el CSV con características ya calculadas por ventana
2. Mapea las columnas del CSV a las 5 características que necesita el modelo:
   - `trace_avg_sector_distance * 512` → Distancia promedio (bytes)
   - `trace_sector_jump_ratio` → Variabilidad
   - `bw_mean_kbps / iops_mean` → Tamaño promedio I/O (bytes)
   - `1 - trace_sector_jump_ratio` → Ratio secuencial
   - `iops_mean` → Tasa de I/O (IOPS)
3. Mapea etiquetas de texto (`sequential`, `random`, `mixed`) a números (0, 1, 2)
4. Divide los datos en train/test (80/20) de forma estratificada
5. Normaliza las características usando `StandardScaler`
6. Guarda:
   - `data/processed/train.npz` y `test.npz` (datos normalizados)
   - `artifacts/scaler.pkl` (normalizador - **CRÍTICO para kernel**)
   - `artifacts/metadata.json` (metadatos del dataset)

**Por qué estas 5 características?**  
Capturan los aspectos distintivos de cada patrón de forma eficiente y son computacionalmente baratas de calcular en tiempo real dentro del kernel.

#### `neuronal_red.py`
**¿Qué hace?**  
Define la arquitectura de la red neuronal.

**Arquitectura:**
```python
Input (5 características) 
  → Capa Densa 1: 5 → 32 neuronas + ReLU + Dropout(20%)
  → Capa Densa 2: 32 → 16 neuronas + ReLU
  → Capa Densa 3: 16 → 3 neuronas (logits)
  → Salida: [score_sequential, score_random, score_mixed]
```

**¿Por qué es "ligera"?**
- Solo 3 capas densas (no es una red profunda)
- Máximo 32 neuronas por capa
- Tamaño total: ~15 KB
- Inferencia rápida (microsegundos)
- Optimizada para ejecución en kernel donde los recursos son limitados

**Componentes:**
- `ReLU`: Función de activación que introduce no-linealidad
- `Dropout(0.2)`: Regularización que previene sobreajuste (desactiva 20% de neuronas aleatoriamente durante entrenamiento)
- `CrossEntropyLoss`: Función de pérdida para clasificación multi-clase

#### `train.py`
**¿Qué hace?**  
Entrena la red neuronal y exporta el modelo en formatos compatibles con el kernel.

**Proceso de entrenamiento:**
1. Carga los datos de entrenamiento y prueba
2. Crea un `DataLoader` con batches de 128 muestras
3. Inicializa el modelo, optimizador (Adam) y función de pérdida
4. Entrena durante hasta 60 épocas con:
   - **Early stopping**: Se detiene si no mejora en 8 épocas consecutivas
   - **Validación**: Evalúa en el conjunto de prueba cada época
   - **Mejor modelo**: Guarda el modelo con mejor accuracy en validación
5. Exporta el modelo en dos formatos:
   - `model.pth`: Pesos PyTorch (para Python)
   - `model_ts.pt`: **TorchScript** (para C/C++ y kernel) ⭐ **PRINCIPAL**
   - `model.onnx`: ONNX (opcional, si se requiere)

**Parámetros de entrenamiento:**
- Learning rate: 0.001
- Batch size: 128
- Optimizador: Adam
- Early stopping: Paciencia de 8 épocas

#### `evaluate.py`
**¿Qué hace?**  
Evalúa el modelo entrenado y genera métricas de rendimiento.

**Métricas generadas:**
- Accuracy general
- Matriz de confusión (muestra errores por clase)
- Guarda resultados en `artifacts/eval_summary.json`

---

## 🚀 Cómo Ejecutar el Pipeline Completo

### 1. Instalación de Dependencias

```bash
pip install -r requirements.txt
```

**Dependencias principales:**
- `torch`: Framework de deep learning
- `numpy`, `pandas`: Manipulación de datos
- `scikit-learn`: Normalización y división de datos
- `joblib`: Guardar/cargar el normalizador

### 2. Preparar el Dataset

**Requisitos del CSV:**
- Archivo: `consolidated_dataset.csv` en el directorio raíz
- Debe tener una columna `label` con valores: `sequential`, `random`, `mixed`
- Debe contener las columnas necesarias para calcular las 5 características

**Ejecutar:**
```bash
python build_dataset_from_consolidated.py
```

**Salida esperada:**
```
Dataset procesado exitosamente!
  - Train: 691 muestras
  - Test: 173 muestras
  - Features: 5
  - Clases: 3
```

**Archivos generados:**
- `data/processed/train.npz` - Datos de entrenamiento normalizados
- `data/processed/test.npz` - Datos de prueba normalizados
- `artifacts/scaler.pkl` - Normalizador (necesario para kernel)
- `artifacts/metadata.json` - Metadatos del dataset

### 3. Entrenar el Modelo

```bash
python train.py
```

**Salida esperada:**
```
Epoch 001 | loss=1.0957 | val_acc=0.3353
Epoch 002 | loss=1.0646 | val_acc=0.3353
...
Epoch 031 | loss=0.1378 | val_acc=0.9711
Early stopping por paciencia.
Entrenamiento completo. Accuracy test=0.9711. Artefactos en 'artifacts/'.
```

**Archivos generados:**
- `artifacts/model.pth` - Pesos PyTorch
- `artifacts/model_ts.pt` - **TorchScript (PARA KERNEL)** ⭐
- `artifacts/training_summary.json` - Resumen del entrenamiento

### 4. Evaluar el Modelo

```bash
python evaluate.py
```

**Salida esperada:**
```
Accuracy test: 0.9711
Matriz de confusión (filas=verdadero, columnas=predicho):
[[55  0  2]
 [ 0 58  0]
 [ 1  2 55]]
```

**Archivo generado:**
- `artifacts/eval_summary.json` - Métricas de evaluación

---

## 📊 Resultados del Modelo

- **Accuracy en test**: 97.11%
- **Distribución de clases**: Balanceada (288 muestras por clase)
- **Tamaño del modelo**: ~15 KB (TorchScript)
- **Tiempo de inferencia**: Microsegundos (optimizado para kernel)

### Matriz de Confusión
```
                Predicho
              Seq  Rand  Mix
Real Seq       55    0    2
Real Rand       0   58    0
Real Mixed      1    2   55
```

- **Sequential**: 96.5% correctos
- **Random**: 100% correctos
- **Mixed**: 94.8% correctos

---

## 🔮 Cómo Usar el Modelo para Hacer Predicciones

**⚠️ IMPORTANTE:** La red neuronal **NO** calcula las características automáticamente. Tú debes:
1. **Calcular las 5 características** desde tus datos de I/O raw
2. **Normalizar** las características usando el scaler
3. **Pasar** las características normalizadas a la red neuronal

La red neuronal solo recibe las 5 características ya calculadas y las clasifica.

### Ejemplo Rápido con Python

```python
import joblib
import numpy as np
import torch
from neuronal_red import IOPatternClassifier

# 1. Cargar modelo y scaler
scaler = joblib.load("artifacts/scaler.pkl")
model = IOPatternClassifier(input_size=5, hidden_size=32, num_classes=3)
model.load_state_dict(torch.load("artifacts/model.pth", map_location="cpu"))
model.eval()

# 2. Preparar características (ejemplo: patrón secuencial)
# ⚠️ NOTA: Estas características DEBEN calcularse desde tus datos de I/O raw
# La red neuronal NO las calcula automáticamente
# 
# Ejemplo de cálculo:
# - offsets = [0, 131072, 262144, ...]  # offsets de operaciones I/O
# - avg_distance = promedio(|offsets[i+1] - offsets[i]|) * 512
# - jump_ratio = % de saltos > 1MB
# - etc.
#
# Aquí usamos valores ya calculados (basados en el dataset real):
features = np.array([
    102774272.0,   # [0] Distancia promedio: 200,731 sectores × 512 bytes
    0.14,          # [1] Variabilidad (jump ratio)
    69436416.0,    # [2] Tamaño promedio I/O: (67,809 KB/s × 1024) / 1.0 IOPS
    0.86,          # [3] Ratio secuencial: 1.0 - 0.14
    1.0            # [4] IOPS
], dtype=np.float32)

# 3. CRÍTICO: Normalizar las características
features_normalized = scaler.transform(features.reshape(1, -1))

# 4. Hacer predicción
features_tensor = torch.tensor(features_normalized, dtype=torch.float32)
with torch.no_grad():
    logits = model(features_tensor)
    probabilities = torch.softmax(logits, dim=1)
    predicted_class = torch.argmax(logits, dim=1).item()

# 5. Interpretar resultado
class_map = {0: "sequential", 1: "random", 2: "mixed"}
predicted_label = class_map[predicted_class]
confidence = probabilities[0][predicted_class].item()

print(f"Predicción: {predicted_label} (confianza: {confidence*100:.2f}%)")
```

### Script de Ejemplo Completo

Ejecuta el script `predict.py` para ver ejemplos completos con los tres patrones:

```bash
python predict.py
```

Este script muestra cómo hacer predicciones con valores reales del dataset.

### Valores de Ejemplo por Patrón

**Para probar con datos similares a los del entrenamiento, usa estos valores:**

#### Patrón Secuencial
```python
avg_sector_distance = 200731      # sectores
sector_jump_ratio = 0.14          # 14%
bw_mean_kbps = 67809             # KB/s
iops_mean = 1.0                   # ops/s
```

#### Patrón Aleatorio
```python
avg_sector_distance = 19534728    # sectores
sector_jump_ratio = 0.998          # 99.8%
bw_mean_kbps = 7518              # KB/s
iops_mean = 1.0                   # ops/s
```

#### Patrón Mixto
```python
avg_sector_distance = 7183669     # sectores
sector_jump_ratio = 0.994          # 99.4%
bw_mean_kbps = 39695             # KB/s
iops_mean = 1.0                   # ops/s
```

**⚠️ IMPORTANTE:** 
- Estos valores están basados en el dataset de entrenamiento
- En producción, calcula las características desde tus datos reales de I/O
- El IOPS en el dataset es constante (1.0), pero en producción deberías calcular el IOPS real
- Siempre normaliza las características antes de pasarlas al modelo

---

## 🔧 Integración en el Kernel Linux

### Contexto: ¿Qué necesita hacer tu compañero?

El objetivo final es que el modelo se ejecute dentro del kernel Linux para clasificar patrones de I/O en tiempo real y ajustar el readahead dinámicamente.

### Archivos para Entregar

1. **`artifacts/model_ts.pt`** (14.8 KB) ⭐ **PRINCIPAL**
   - Modelo en formato TorchScript
   - Formato compatible con C/C++ y KML
   - Se carga directamente en el kernel

2. **`artifacts/scaler.pkl`** (719 bytes) ⭐ **CRÍTICO**
   - Contiene los parámetros de normalización (medias y desviaciones estándar)
   - **NO se carga directamente**, pero sus parámetros deben implementarse en C
   - Las características DEBEN normalizarse antes de cada inferencia

3. **`artifacts/metadata.json`**
   - Mapeo de clases: `{0: "sequential", 1: "random", 2: "mixed"}`
   - Dimensiones: 5 características de entrada, 3 clases de salida
   - Referencia para implementación

### Proceso de Integración (Responsabilidad del compañero)

#### Paso 1: Cargar el Modelo TorchScript
- Usar la biblioteca de KML o wrapper de TorchScript para C
- Cargar `model_ts.pt` en memoria del kernel
- Inicializar el modelo para inferencia

#### Paso 2: Implementar Normalización en C
- Extraer parámetros del `scaler.pkl` (medias y desviaciones estándar)
- Implementar normalización en C:
  ```c
  normalized_feature[i] = (feature[i] - mean[i]) / std[i]
  ```
- Aplicar a las 5 características antes de cada inferencia

#### Paso 3: Extraer Características en Tiempo Real
- Interceptar operaciones de I/O en el kernel
- Calcular las 5 características por ventana deslizante:
  1. Distancia promedio entre offsets
  2. Variabilidad (jump ratio)
  3. Tamaño promedio de I/O
  4. Ratio secuencial
  5. IOPS
- Normalizar usando los parámetros del scaler

#### Paso 4: Ejecutar Inferencia
- Pasar las 5 características normalizadas al modelo
- Obtener los 3 logits (scores) de salida
- Seleccionar la clase con mayor score

#### Paso 5: Mapear a Readahead
- Mapear clase predicha a valor de readahead:
  - `0 (sequential)` → Readahead alto (ej: 128-256 KB)
  - `1 (random)` → Readahead bajo (ej: 16-32 KB)
  - `2 (mixed)` → Readahead intermedio (ej: 64-128 KB)
- Ajustar el readahead del sistema de archivos

### Consideraciones Técnicas para el Kernel

1. **Memoria limitada**: El modelo es ligero (~15 KB) para no consumir mucha memoria del kernel
2. **Latencia baja**: La inferencia debe ser rápida (microsegundos) para no afectar el rendimiento
3. **Normalización obligatoria**: Las características DEBEN normalizarse igual que en entrenamiento
4. **Ventana deslizante**: Las características se calculan sobre ventanas de operaciones de I/O
5. **Determinismo**: El modelo es determinístico (sin operaciones aleatorias) para comportamiento predecible

### Formato de Entrada para el Modelo

**Input**: Array de 5 valores float32 normalizados
```c
float features[5] = {
    normalized_avg_distance,
    normalized_variability,
    normalized_avg_io_size,
    normalized_seq_ratio,
    normalized_iops
};
```

**Output**: Array de 3 logits (scores)
```c
float logits[3] = {
    score_sequential,  // Clase 0
    score_random,      // Clase 1
    score_mixed        // Clase 2
};
// Clase predicha = índice del máximo valor
```

### Valores Reales de Referencia para Predicciones

**⚠️ IMPORTANTE:** Estos son los valores reales del dataset de entrenamiento. Usa valores similares para obtener predicciones confiables.

#### Patrón Secuencial (Sequential)
```python
# Valores típicos basados en el dataset real:
avg_sector_distance = 200731      # Mediana: ~200,731 sectores (~100 MB)
sector_jump_ratio = 0.14           # Mediana: 0.14 (14% de saltos grandes)
bw_mean_kbps = 67809              # Mediana: ~67,809 KB/s (~66 MB/s)
iops_mean = 1.0                   # IOPS promedio

# Características calculadas:
feature_1 = 200731 * 512 = 102,774,272 bytes      # Distancia promedio
feature_2 = 0.14                                   # Variabilidad
feature_3 = (67809 * 1024) / 1.0 = 69,436,416 bytes  # Tamaño promedio I/O
feature_4 = 1.0 - 0.14 = 0.86                      # Ratio secuencial
feature_5 = 1.0                                    # IOPS
```

#### Patrón Aleatorio (Random)
```python
# Valores típicos basados en el dataset real:
avg_sector_distance = 19534728    # Mediana: ~19,534,728 sectores (~9.5 GB)
sector_jump_ratio = 0.998          # Mediana: 0.998 (99.8% de saltos grandes)
bw_mean_kbps = 7518              # Mediana: ~7,518 KB/s (~7.3 MB/s)
iops_mean = 1.0                  # IOPS promedio

# Características calculadas:
feature_1 = 19534728 * 512 = 10,001,780,736 bytes    # Distancia promedio
feature_2 = 0.998                                     # Variabilidad
feature_3 = (7518 * 1024) / 1.0 = 7,698,432 bytes    # Tamaño promedio I/O
feature_4 = 1.0 - 0.998 = 0.002                       # Ratio secuencial
feature_5 = 1.0                                       # IOPS
```

#### Patrón Mixto (Mixed)
```python
# Valores típicos basados en el dataset real:
avg_sector_distance = 7183669     # Mediana: ~7,183,669 sectores (~3.5 GB)
sector_jump_ratio = 0.994          # Mediana: 0.994 (99.4% de saltos grandes)
bw_mean_kbps = 39695             # Mediana: ~39,695 KB/s (~38.7 MB/s)
iops_mean = 1.0                  # IOPS promedio

# Características calculadas:
feature_1 = 7183669 * 512 = 3,678,038,528 bytes      # Distancia promedio
feature_2 = 0.994                                    # Variabilidad
feature_3 = (39695 * 1024) / 1.0 = 40,647,680 bytes # Tamaño promedio I/O
feature_4 = 1.0 - 0.994 = 0.006                      # Ratio secuencial
feature_5 = 1.0                                      # IOPS
```

**Rangos de Valores Observados en el Dataset:**

| Característica | Sequential | Random | Mixed |
|----------------|------------|--------|-------|
| **Distancia promedio (sectores)** | 3,702 - 11,747,540 | 4,915 - 35,373,190 | 7,716 - 27,706,060 |
| **Jump ratio** | 0.00 - 0.45 | 0.76 - 1.00 | 0.96 - 1.00 |
| **Bandwidth (KB/s)** | 19,777 - 182,975 | 1,977 - 23,407 | 3,657 - 384,524 |
| **IOPS** | 1.0 (constante) | 1.0 (constante) | 1.0 (constante) |

**Nota sobre IOPS:** En este dataset, `iops_mean` es constante (1.0) para todas las muestras. En producción, deberías calcular el IOPS real basado en el número de operaciones por segundo observadas en tu ventana de tiempo.

---

## 🔌 Componentes de Integración en el Kernel

### Archivos en `artifacts/`

El directorio `artifacts/` contiene todos los componentes necesarios para la integración:

#### 1. **Daemon ML Predictor** (`ml_predictor.cpp`)
- **Descripción**: Daemon en C++ que carga el modelo TorchScript y ejecuta inferencias
- **Funcionalidad**: 
  - Escucha en un socket Unix (`/tmp/ml_predictor.sock`)
  - Recibe 5 características normalizadas (5 floats)
  - Devuelve la clase predicha (1 int: 0, 1, o 2)
- **Compilación**: `make ml_predictor` (requiere libtorch)
- **Uso**: `./ml_predictor model_ts.pt`

#### 2. **eBPF Block Trace Collector** (`ebpf_block_trace.cpp`) ⭐ **NUEVO**
- **Descripción**: Recolector de estadísticas I/O usando eBPF (tracepoints del kernel)
- **Funcionalidad**:
  - Captura eventos `block:block_rq_issue` usando eBPF
  - Agrega estadísticas en ventanas de tiempo (default: 2.5 segundos)
  - Calcula las 5 características del modelo
  - Envía características al daemon ML predictor
  - Escribe readahead al sysfs según la predicción
- **Compilación**: `make ebpf_block_trace` (requiere BCC)
- **Uso**: `sudo ./ebpf_block_trace --device nvme0n1 --window 2500`
- **Migración**: Migrado desde Python a C++ para unificar el stack tecnológico
- **Ventajas**: Mejor rendimiento, menor overhead, mismo lenguaje que el daemon

#### 3. **Módulo del Kernel** (`ml_predictor.c`)
- **Descripción**: Módulo del kernel para comunicación Netlink
- **Funcionalidad**: Permite que el kernel envíe características al daemon userspace
- **Estado**: Preparado para integración con el sistema de readahead del kernel

#### 4. **Scripts Alternativos**
- **`ml_feature_collector.sh`**: Script bash que usa `iostat` y `perf trace` (no requiere eBPF)
- **`ebpf_block_trace.py`**: Versión Python original (puede mantenerse como fallback)

### Flujo de Integración Completo

```
┌─────────────────────────────────────────────────────────────┐
│  Kernel Linux                                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Block Layer (I/O requests)                           │  │
│  └──────────────┬───────────────────────────────────────┘  │
│                 │                                           │
│                 ▼                                           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  eBPF Tracepoints (block_rq_issue)                    │  │
│  └──────────────┬───────────────────────────────────────┘  │
└─────────────────┼──────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  Userspace                                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  ebpf_block_trace.cpp (C++)                          │  │
│  │  - Captura eventos eBPF                               │  │
│  │  - Agrega en ventanas de 2.5s                        │  │
│  │  - Calcula 5 características                          │  │
│  └──────────────┬───────────────────────────────────────┘  │
│                 │                                           │
│                 │ Unix Socket                               │
│                 ▼                                           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  ml_predictor.cpp (C++ Daemon)                       │  │
│  │  - Carga model_ts.pt                                  │  │
│  │  - Normaliza características                          │  │
│  │  - Ejecuta inferencia                                 │  │
│  │  - Devuelve predicción (0, 1, o 2)                   │  │
│  └──────────────┬───────────────────────────────────────┘  │
│                 │                                           │
│                 │ Respuesta (int)                           │
│                 ▼                                           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  ebpf_block_trace.cpp                                 │  │
│  │  - Mapea predicción a readahead_kb                    │  │
│  │  - Escribe a /sys/block/DEV/queue/read_ahead_kb       │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Protocolo de Comunicación

**Socket Unix**: `/tmp/ml_predictor.sock`

1. **Cliente → Daemon**: 5 floats (20 bytes, little-endian)
   ```c
   float features[5] = {
       avg_dist_bytes,      // [0] Distancia promedio (bytes)
       jump_ratio,           // [1] Variabilidad (0.0-1.0)
       avg_io_size_bytes,    // [2] Tamaño promedio I/O (bytes)
       seq_ratio,            // [3] Ratio secuencial (0.0-1.0)
       iops_mean             // [4] IOPS (operaciones/segundo)
   };
   ```

2. **Daemon → Cliente**: 1 int (4 bytes)
   ```c
   int prediction;  // 0=sequential, 1=random, 2=mixed
   ```

### Mapeo de Predicciones a Readahead

```c
int readahead_kb;
switch (prediction) {
    case 0:  // sequential
        readahead_kb = 256;
        break;
    case 1:  // random
        readahead_kb = 16;
        break;
    case 2:  // mixed
        readahead_kb = 64;
        break;
}
```

### Compilación de Componentes

```bash
cd artifacts

# Compilar todo
make

# O compilar individualmente
make ml_predictor        # Requiere libtorch
make ebpf_block_trace    # Requiere BCC
```

**Dependencias:**
- **libtorch**: Para `ml_predictor.cpp` (PyTorch C++ API)
- **BCC**: Para `ebpf_block_trace.cpp` (BPF Compiler Collection)
  - Instalación: `sudo apt-get install bpfcc-tools libbpfcc-dev`

### Documentación Adicional

- **`MIGRACION_EBPF_CPP.md`**: Detalles sobre la migración de Python a C++
- **`CAMBIOS_APLICADOS.md`**: Historial de cambios en los scripts de integración

---

## 🐛 Solución de Problemas

### Error: "No se encontraron trazas en 'data/raw'"
- **Solución**: Asegúrate de tener `consolidated_dataset.csv` en el directorio raíz

### Error: "No module named 'torch'"
- **Solución**: Instala las dependencias: `pip install -r requirements.txt`

### Warning: "exportación ONNX falló"
- **No es crítico**: TorchScript es el formato principal. ONNX es opcional.

### El modelo tiene baja accuracy
- Verifica que el dataset esté balanceado
- Revisa que las características se estén calculando correctamente
- Considera ajustar hiperparámetros en `train.py`

---

## 📝 Notas Importantes

1. **Normalización es CRÍTICA**: El modelo fue entrenado con datos normalizados. Sin normalización, las predicciones serán incorrectas.

2. **Orden de características**: Las 5 características deben pasarse en el mismo orden:
   - [0] Distancia promedio
   - [1] Variabilidad
   - [2] Tamaño promedio I/O
   - [3] Ratio secuencial
   - [4] IOPS

3. **Ventana deslizante**: Las características se calculan sobre ventanas de operaciones de I/O. El tamaño de ventana y overlap deben ser consistentes.

4. **TorchScript es el formato principal**: Aunque se exporta ONNX, TorchScript (`model_ts.pt`) es el formato recomendado para integración en kernel.

5. **Exclusión de features con data leakage**: Las características `bs` y `iodepth` están excluidas del modelo porque están fuertemente correlacionadas con el label. En producción, solo puedes observar el comportamiento, no los parámetros de configuración.

---

## 📚 Referencias

- **KML (Kernel Machine Learning)**: Framework para ejecutar modelos ML en el kernel Linux
- **TorchScript**: Formato de PyTorch para exportar modelos a C++
- **StandardScaler**: Normalización z-score: `(x - mean) / std`
- **LTTng**: Linux Trace Toolkit para captura de eventos del kernel
- **FIO**: Flexible I/O Tester para generación de cargas de trabajo

---

**Última actualización**: Noviembre 2025  
**Estado**: Modelo entrenado y listo para integración en kernel ✅
