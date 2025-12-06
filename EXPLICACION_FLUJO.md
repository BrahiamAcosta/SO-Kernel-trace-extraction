# Explicación: ¿Qué hace la Red Neuronal vs. Extracción de Características?

## 🔍 Respuesta Corta

**NO**, la red neuronal **NO** hace la preparación de características. La red neuronal solo recibe las 5 características ya calculadas y las clasifica.

## 📊 Flujo Completo de Datos

```
┌─────────────────────────────────────────────────────────────┐
│ 1. DATOS RAW (Operaciones de I/O)                          │
│    - Lista de offsets: [1000, 1008, 1016, 5000, 5008, ...] │
│    - Tamaños de I/O: [131072, 131072, 131072, ...]         │
│    - Timestamps: [0.0, 0.1, 0.2, 0.3, ...]                 │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. EXTRACCIÓN DE CARACTERÍSTICAS (TU RESPONSABILIDAD)       │
│    ⚠️ Esto NO lo hace la red neuronal                       │
│                                                              │
│    Cálculos manuales:                                        │
│    - Distancia promedio = promedio(|offset[i+1] - offset[i]|)│
│    - Jump ratio = % de saltos > 1MB                         │
│    - Tamaño promedio I/O = promedio(tamaños)               │
│    - Ratio secuencial = 1 - jump_ratio                      │
│    - IOPS = número_operaciones / tiempo                     │
│                                                              │
│    Resultado: Array de 5 valores                            │
│    [distancia, variabilidad, tamaño, ratio_sec, iops]       │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. NORMALIZACIÓN (OBLIGATORIA)                              │
│    Usa el scaler entrenado:                                  │
│    normalized = (valor - media) / desviación_estándar        │
│                                                              │
│    Resultado: Array de 5 valores normalizados               │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. RED NEURONAL (Solo clasificación)                        │
│    ✅ Esto SÍ lo hace la red neuronal                       │
│                                                              │
│    Input: [5 características normalizadas]                  │
│    ↓                                                         │
│    Capa 1: 5 → 32 neuronas                                   │
│    ↓                                                         │
│    Capa 2: 32 → 16 neuronas                                  │
│    ↓                                                         │
│    Capa 3: 16 → 3 logits                                    │
│    ↓                                                         │
│    Output: [score_sequential, score_random, score_mixed]    │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. PREDICCIÓN                                                │
│    Clase = índice del máximo logit                          │
│    Probabilidad = softmax(logits)                            │
└─────────────────────────────────────────────────────────────┘
```

## 🎯 División de Responsabilidades

### Tu Responsabilidad (Antes de la Red Neuronal)

1. **Interceptar operaciones de I/O** en el kernel
2. **Calcular las 5 características** desde los datos raw:
   ```python
   # Ejemplo: calcular distancia promedio
   offsets = [1000, 1008, 1016, 5000, 5008]
   distances = [abs(offsets[i+1] - offsets[i]) for i in range(len(offsets)-1)]
   avg_distance = sum(distances) / len(distances) * 512  # convertir a bytes
   ```
3. **Normalizar** usando el scaler entrenado
4. **Pasar al modelo** las 5 características normalizadas

### Responsabilidad de la Red Neuronal

1. **Recibir** las 5 características normalizadas
2. **Procesar** a través de las 3 capas
3. **Clasificar** en una de las 3 clases
4. **Retornar** los scores/probabilidades

## 💻 Código de Ejemplo Completo

```python
# ============================================
# PASO 1: TÚ calculas las características
# ============================================
# Supongamos que tienes operaciones de I/O reales
io_operations = [
    {"offset": 0, "size": 131072, "timestamp": 0.0},
    {"offset": 131072, "size": 131072, "timestamp": 0.1},
    {"offset": 262144, "size": 131072, "timestamp": 0.2},
    # ... más operaciones
]

# Calcular características manualmente
offsets = [op["offset"] for op in io_operations]
sizes = [op["size"] for op in io_operations]
timestamps = [op["timestamp"] for op in io_operations]

# Feature 1: Distancia promedio
distances = [abs(offsets[i+1] - offsets[i]) for i in range(len(offsets)-1)]
avg_distance = sum(distances) / len(distances)  # en bytes

# Feature 2: Jump ratio
large_jumps = [d for d in distances if d > 1024 * 1024]  # > 1MB
jump_ratio = len(large_jumps) / len(distances) if distances else 0.0

# Feature 3: Tamaño promedio I/O
avg_size = sum(sizes) / len(sizes)  # en bytes

# Feature 4: Ratio secuencial
seq_ratio = 1.0 - jump_ratio

# Feature 5: IOPS
duration = timestamps[-1] - timestamps[0]
iops = len(io_operations) / duration if duration > 0 else 0.0

# Array de características (SIN normalizar aún)
features = np.array([avg_distance, jump_ratio, avg_size, seq_ratio, iops])

# ============================================
# PASO 2: TÚ normalizas
# ============================================
scaler = joblib.load("artifacts/scaler.pkl")
features_normalized = scaler.transform(features.reshape(1, -1))

# ============================================
# PASO 3: LA RED NEURONAL clasifica
# ============================================
model = IOPatternClassifier(...)
model.load_state_dict(torch.load("artifacts/model.pth"))
model.eval()

with torch.no_grad():
    features_tensor = torch.tensor(features_normalized, dtype=torch.float32)
    logits = model(features_tensor)  # ← La red neuronal solo hace esto
    predicted_class = torch.argmax(logits, dim=1).item()
```

## 🔑 Puntos Clave

1. **La red neuronal es "tonta"**: Solo sabe recibir 5 números y clasificarlos. No sabe calcular distancias, jump ratios, etc.

2. **La "inteligencia" está en las características**: El modelo aprendió a distinguir patrones basándose en esas 5 características específicas. Si le das características diferentes o mal calculadas, fallará.

3. **En el kernel Linux**: Tu compañero debe implementar el cálculo de características en C, no la red neuronal (que ya está entrenada).

4. **Por qué es así**: 
   - Las características son **específicas del dominio** (I/O patterns)
   - La red neuronal es **genérica** (puede clasificar cualquier cosa con 5 números)
   - Separar responsabilidades hace el sistema más modular y eficiente

## 📝 Resumen

| Componente | Responsabilidad |
|------------|----------------|
| **Tú / Kernel** | Calcular las 5 características desde operaciones de I/O raw |
| **Scaler** | Normalizar las características |
| **Red Neuronal** | Clasificar las características normalizadas en 3 clases |

**La función `prepare_features_from_raw_data()` en `predict.py` es solo una ayuda para calcular las características. La red neuronal NO la ejecuta automáticamente.**

