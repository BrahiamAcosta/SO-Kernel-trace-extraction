# Cómo Usar el Modelo para Hacer Predicciones

Esta guía explica cómo usar el modelo entrenado para predecir patrones de I/O a partir de datos nuevos.

---

## 📋 Resumen Rápido

Para hacer una predicción necesitas:

1. **Calcular las 5 características** a partir de una ventana de operaciones de I/O
2. **Normalizar** las características usando el scaler
3. **Pasar al modelo** y obtener la predicción

---

## 🔢 Las 5 Características que Necesitas

El modelo espera exactamente estas 5 características en este orden:

### 1. Distancia promedio entre offsets (en bytes)
- **Cómo calcular**: Toma los offsets de las operaciones de I/O en una ventana, calcula las distancias entre consecutivos, y promedia el valor absoluto
- **Ejemplo secuencial**: ~5,120 bytes (10 sectores × 512 bytes)
- **Ejemplo aleatorio**: ~25,600,000 bytes (50,000 sectores × 512 bytes)

### 2. Variabilidad (jump ratio) (0.0 - 1.0)
- **Cómo calcular**: Porcentaje de saltos grandes (>1MB) entre accesos consecutivos
- **Ejemplo secuencial**: 0.05 (5% de saltos grandes)
- **Ejemplo aleatorio**: 0.90 (90% de saltos grandes)

### 3. Tamaño promedio de I/O (en bytes)
- **Cómo calcular**: Promedio del tamaño de cada operación de I/O en la ventana
- **Alternativa**: Si no tienes el tamaño directo, calcula: `(bandwidth_kbps × 1024) / iops`
- **Ejemplo secuencial**: ~1,280,000 bytes (1.28 MB por operación)
- **Ejemplo aleatorio**: ~5,120 bytes (4 KB por operación)

### 4. Ratio secuencial (0.0 - 1.0)
- **Cómo calcular**: `1 - jump_ratio` (inverso de la variabilidad)
- **Ejemplo secuencial**: 0.95 (95% de accesos secuenciales)
- **Ejemplo aleatorio**: 0.10 (10% de accesos secuenciales)

### 5. IOPS (operaciones por segundo)
- **Cómo calcular**: Número de operaciones de I/O por segundo en la ventana
- **Ejemplo secuencial**: 400 ops/s
- **Ejemplo aleatorio**: 3,000 ops/s

---

## 💻 Código de Ejemplo

### Opción 1: Usar el script `predict.py`

```bash
python predict.py
```

Este script muestra ejemplos completos de cómo hacer predicciones.

### Opción 2: Usar en tu propio código

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

# 2. Preparar tus características (ejemplo: patrón secuencial)
features = np.array([
    5120.0,      # [0] Distancia promedio: 5120 bytes
    0.05,        # [1] Variabilidad: 0.05
    1280000.0,   # [2] Tamaño promedio I/O: 1.28 MB
    0.95,        # [3] Ratio secuencial: 0.95
    400.0        # [4] IOPS: 400
], dtype=np.float32)

# 3. CRÍTICO: Normalizar las características
features_normalized = scaler.transform(features.reshape(1, -1))

# 4. Convertir a tensor y hacer predicción
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

---

## 📊 Ejemplos de Valores Típicos

### Patrón Secuencial
```python
features = [
    5120.0,      # Distancia pequeña
    0.05,        # Bajo jump ratio
    1280000.0,   # Requests grandes
    0.95,        # Alto ratio secuencial
    400.0        # Bajo IOPS
]
# Resultado esperado: "sequential" con alta confianza
```

### Patrón Aleatorio
```python
features = [
    25600000.0,  # Distancia grande
    0.90,        # Alto jump ratio
    5120.0,      # Requests pequeños
    0.10,        # Bajo ratio secuencial
    3000.0       # Alto IOPS
]
# Resultado esperado: "random" con alta confianza
```

### Patrón Mixto
```python
features = [
    1024000.0,   # Distancia intermedia
    0.50,        # Jump ratio intermedio
    102400.0,    # Requests medianos
    0.50,        # Ratio secuencial intermedio
    1500.0       # IOPS intermedio
]
# Resultado esperado: "mixed" con confianza moderada
```

---

## ⚠️ Puntos Críticos

### 1. Normalización es OBLIGATORIA
**❌ INCORRECTO:**
```python
features = np.array([5120.0, 0.05, 1280000.0, 0.95, 400.0])
prediction = model(torch.tensor(features))  # ← ERROR: Sin normalizar
```

**✅ CORRECTO:**
```python
features = np.array([5120.0, 0.05, 1280000.0, 0.95, 400.0])
features_normalized = scaler.transform(features.reshape(1, -1))  # ← Normalizar primero
prediction = model(torch.tensor(features_normalized))
```

### 2. Orden de Características
Las características **DEBEN** estar en este orden exacto:
- [0] Distancia promedio
- [1] Variabilidad
- [2] Tamaño promedio I/O
- [3] Ratio secuencial
- [4] IOPS

### 3. Tipo de Datos
- Usa `float32` (no `float64` o `int`)
- El array debe tener shape `(5,)` o `(1, 5)`

### 4. Ventana de Datos
- Las características deben calcularse sobre una **ventana de operaciones de I/O**
- Recomendado: últimas 32 operaciones (o ventana de 2.5 segundos)
- Debe ser consistente con cómo se entrenó el modelo

---

## 🔍 Interpretación de Resultados

El modelo retorna:
- **Clase predicha**: 0 (sequential), 1 (random), o 2 (mixed)
- **Probabilidades**: Distribución de probabilidad sobre las 3 clases
- **Confianza**: Probabilidad de la clase predicha

**Ejemplo de salida:**
```
Predicción: sequential
Confianza: 95.23%
Probabilidades:
  sequential: 95.23%
  random:     2.10%
  mixed:      2.67%
```

**Interpretación:**
- Si la confianza es > 80%: Predicción muy confiable
- Si la confianza es 50-80%: Predicción moderada (puede ser patrón mixto o transición)
- Si la confianza es < 50%: Revisar los datos de entrada

---

## 🧪 Probar con Datos Reales

Si tienes datos reales de operaciones de I/O:

1. **Agrupa en ventanas**: Toma las últimas N operaciones (ej: 32)
2. **Calcula las 5 características** según las fórmulas arriba
3. **Usa el script `predict.py`** o el código de ejemplo
4. **Interpreta el resultado**

**Ejemplo con datos reales:**
```python
# Supongamos que tienes una lista de operaciones de I/O
io_operations = [
    {"offset": 0, "size": 131072, "timestamp": 0.0},
    {"offset": 131072, "size": 131072, "timestamp": 0.1},
    {"offset": 262144, "size": 131072, "timestamp": 0.2},
    # ... más operaciones
]

# Calcular características
offsets = [op["offset"] for op in io_operations]
distances = [abs(offsets[i+1] - offsets[i]) for i in range(len(offsets)-1)]
avg_distance = np.mean(distances)

# ... calcular las otras 4 características ...

# Hacer predicción
features = np.array([avg_distance, jump_ratio, avg_size, seq_ratio, iops])
result = predict(model, scaler, features, metadata)
```

---

## 📝 Resumen

**Para hacer una predicción:**

1. ✅ Calcula las 5 características de una ventana de I/O
2. ✅ Crea un array numpy: `np.array([f1, f2, f3, f4, f5], dtype=np.float32)`
3. ✅ Normaliza: `scaler.transform(features.reshape(1, -1))`
4. ✅ Pasa al modelo: `model(torch.tensor(features_normalized))`
5. ✅ Interpreta: `torch.argmax(logits)` para la clase, `torch.softmax(logits)` para probabilidades

**¡Listo!** 🎉

