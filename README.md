# Pipeline de ML para Clasificación de Patrones de I/O

Sistema de aprendizaje automático para clasificar patrones de acceso a disco (secuencial, aleatorio, mixto) y optimizar el readahead en el kernel Linux mediante KML (Kernel Machine Learning).

---

## 📋 Contexto General del Proyecto

Este proyecto desarrolla un componente de red neuronal que clasifica patrones de I/O en tiempo real dentro del kernel Linux. El objetivo es predecir el tipo de patrón de acceso (sequential, random, mixed) para ajustar dinámicamente el valor de readahead y mejorar el rendimiento del sistema de archivos.

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
  - `0 (sequential)` → Readahead alto (ej: 128 KB)
  - `1 (random)` → Readahead bajo (ej: 4 KB)
  - `2 (mixed)` → Readahead intermedio (ej: 32 KB)
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

---

## 📚 Referencias

- **KML (Kernel Machine Learning)**: Framework para ejecutar modelos ML en el kernel Linux
- **TorchScript**: Formato de PyTorch para exportar modelos a C++
- **StandardScaler**: Normalización z-score: `(x - mean) / std`

---

**Última actualización**: Noviembre 2025  
**Estado**: Modelo entrenado y listo para integración en kernel ✅
