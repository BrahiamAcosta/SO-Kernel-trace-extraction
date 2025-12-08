# 💻 Implementación de Red Neuronal para Optimización Dinámica del Parámetro Read-Ahead en Linux

## Resumen del Proyecto

Este proyecto implementa un sistema inteligente que usa una red neuronal para ajustar dinámicamente el parámetro `read_ahead_kb` del kernel de Linux según el patrón de acceso a disco detectado. El sistema captura eventos de I/O en tiempo real usando eBPF, predice el patrón de acceso (secuencial, aleatorio o mixto) mediante un modelo de deep learning, y ajusta automáticamente el read-ahead para optimizar el rendimiento.

---

## Fase 1: Captura y Preparación del Dataset

### 1.1 Objetivo

Generar un dataset etiquetado con trazas reales del sistema operativo que representen tres patrones distintos de acceso a disco:

- **Sequential (secuencial)**: Lecturas consecutivas, típicas de streaming o backups.
- **Random (aleatorio)**: Accesos no consecutivos, típicos de bases de datos.
- **Mixed (mixto)**: Combinación de ambos patrones.

### 1.2 Herramientas Utilizadas

**LTTng (Linux Trace Toolkit Next Generation)**:

- Sistema de tracing del kernel de Linux de bajo overhead.
- Captura eventos a nivel kernel sin degradar significativamente el rendimiento.
- Permite registrar eventos de block layer, syscalls y operaciones de I/O.

**FIO (Flexible I/O Tester)**:

- Generador de carga de I/O sintética.
- Permite simular patrones específicos de manera controlada.
- Configurable para diferentes tamaños de bloque, profundidad de cola, y tipos de operación.

### 1.3 Proceso de Captura

El script `capture_training_dataset.sh` automatiza todo el proceso:

#### Configuración de Sesiones LTTng

```bash
# Se crea una sesión única por cada experimento
lttng create readahead_train_sequential_1_cold
```

Para cada patrón se habilitan eventos relevantes:

- **Block layer**: `block_rq_insert`, `block_rq_issue`, `block_rq_complete`.
- **Bio (Block I/O)**: `block_bio_frontmerge`, `block_bio_backmerge`.
- **Read-ahead**: Eventos relacionados con readahead y page_cache.
- **Syscalls**: `read`, `pread64`, `readv`, `preadv`.

#### Generación de Patrones con FIO

| Patrón     | Configuración FIO                            | Descripción                                                                        |
| ---------- | -------------------------------------------- | ---------------------------------------------------------------------------------- |
| Sequential | `rw=read, bs=128k, iodepth=4, numjobs=2`     | Lectura secuencial con bloques grandes (óptimo para secuencial).                   |
| Random     | `rw=randread, bs=4k, iodepth=16, numjobs=2`  | Lectura aleatoria con bloques pequeños (típico de BD) y mayor profundidad de cola. |
| Mixed      | `rw=randrw, rwmixread=70, bs=64k, iodepth=8` | Mezcla de lectura/escritura aleatoria, tamaño intermedio.                          |

#### Estrategia de Captura

Para cada patrón se ejecutan **3 runs** con dos modos:

- **Cold cache**: Cache del sistema limpiado antes del test:
  ```bash
  sync
  echo 3 > /proc/sys/vm/drop_caches
  ```
- **Warm cache**: Sin limpiar cache (simula uso real).

Esto genera **18 trazas totales** (3 patrones × 3 runs × 2 modos).

#### Metadatos Capturados

Para cada experimento se registra en `metadata.csv` para trazabilidad completa:

- Timestamp del experimento
- Patrón ejecutado
- Modo (cold/warm)
- Configuración FIO (bs, iodepth, numjobs)
- Estado del sistema (CPU cores, memoria libre)
- Cantidad de eventos capturados
- Tamaño de la traza

### 1.4 Consolidación del Dataset

El script `consolidate_v2.py` procesa todas las trazas y extrae características por ventana temporal de **2.5 segundos**, calculando estadísticas agregadas:

| Característica       | Descripción                                                |
| -------------------- | ---------------------------------------------------------- |
| `avg_distance_bytes` | Distancia promedio entre sectores consecutivos (en bytes). |
| `jump_ratio`         | Proporción de "saltos grandes" (>1 MB entre accesos).      |
| `avg_io_bytes`       | Tamaño promedio de cada operación de I/O.                  |
| `seq_ratio`          | Ratio de accesos secuenciales (1 - jump_ratio).            |
| `iops`               | Operaciones de I/O por segundo.                            |

**Output final**: `dataset.csv` con formato:

```csv
avg_distance_bytes,jump_ratio,avg_io_bytes,seq_ratio,iops,label
524288,0.05,131072,0.95,45.2,sequential
8192,0.85,4096,0.15,1250.5,random
65536,0.45,65536,0.55,320.8,mixed
```

---

## Fase 2: Desarrollo de la Red Neuronal

En esta fase se diseñó, entrenó y validó un modelo de clasificación de deep learning capaz de predecir el patrón de acceso a partir de las 5 características extraídas.

### Características del Modelo

El modelo fue entrenado usando **PyTorch**, implementando una red neuronal feedforward con las siguientes características:

- **Arquitectura**: Red densa (fully connected) con múltiples capas ocultas.
- **Entrada**: 5 características normalizadas.
- **Salida**: 3 clases (sequential, random, mixed).
- **Función de pérdida**: Cross-entropy para clasificación multiclase.
- **Optimizador**: Adam con learning rate adaptativo.
- **Normalización**: StandardScaler para estandarizar features.

El modelo entrenado alcanzó métricas de rendimiento adecuadas y fue exportado a formato **TorchScript** para su uso en C++.

---

## Fase 3: Integración en el Sistema Operativo

### 3.1 Arquitectura del Sistema

El sistema opera en dos espacios principales: **Kernel Space** y **User Space**, comunicados mediante perf buffer y un Unix Socket.

### 3.2 Componente 1: ML Predictor Daemon

El daemon se encarga de recibir las características, normalizarlas y ejecutar la inferencia del modelo.

#### Carga del Modelo TorchScript

**Ventajas de TorchScript**: Permite ejecutar modelos PyTorch en C++ sin dependencias de Python, ofreciendo mayor rendimiento y menor latencia.

**Proceso de conversión** (en Python):

```python
# En Python (durante entrenamiento)
traced_model = torch.jit.trace(model, example_input)
traced_model.save("model_ts.pt")
```

**Carga en C++**:

```cpp
torch::jit::script::Module model;
model = torch::jit::load("model_ts.pt");
model.eval(); // Modo evaluación (sin dropout)
```

#### Normalización de Features

El daemon debe aplicar la misma normalización (StandardScaler) utilizada en el entrenamiento, usando medias y desviaciones estándar pre-calculadas:

```cpp
// Normalización:
normalized[i] = (raw[i] - FEATURE_MEANS[i]) / FEATURE_STDS[i]
```

Esto es **crítico** para la precisión del modelo.

#### Comunicación por Unix Socket

**Ventajas**: Latencia ultra-baja, no requiere permisos especiales, ideal para Comunicación Entre Procesos (IPC) local.

**Protocolo definido**:

- Cliente → Daemon: 5 floats (20 bytes) `[avg_distance][jump_ratio][avg_io][seq_ratio][iops]`
- Daemon → Cliente: 1 int (4 bytes) `[predicted_class]`

#### Inferencia Optimizada

Se utiliza la guarda `torch::NoGradGuard` para desactivar el cálculo de gradientes y acelerar la inferencia, logrando un rendimiento típico de **~100-500 microsegundos** por predicción.

#### Servicio Systemd

El daemon se gestiona mediante systemd para asegurar su correcta inicialización y reinicio automático:

```ini
[Unit]
Description=ML Predictor Daemon for Read-Ahead Optimization
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/ml_predictor /path/to/model_ts.pt
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

### 3.3 Componente 2: eBPF Block Trace Collector

Este componente captura la actividad de I/O, calcula las características en tiempo real y realiza el ajuste del parámetro.

#### Captura de Eventos con eBPF

**Ventajas de eBPF**: Ejecución en kernel space con overhead mínimo y acceso directo a eventos sin necesidad de recompilar el kernel.

**Tracepoint utilizado**: `block_rq_complete`

**Campos capturados**: `sector`, `bytes`, `ts` (timestamp de alta resolución), `rw` (tipo de operación).

```c
TRACEPOINT_PROBE(block, block_rq_complete) {
    struct io_event info = {};
    info.sector = args->sector;
    info.bytes = args->nr_sector * 512;
    info.ts = bpf_ktime_get_ns();

    // Enviar a userspace
    events.perf_submit(args, &info, sizeof(info));
    return 0;
}
```

#### Cálculo de Características en Tiempo Real

El collector mantiene una ventana deslizante de **2.5 segundos** y calcula las 5 características con cada evento:

```cpp
// Detectar salto (>1MB de distancia)
if (stats.last_sector != 0) {
    long long diff = abs(e.sector - stats.last_sector);
    if (diff * 512 > 1000000) { // 1MB threshold
        stats.jumps++;
    }
}
stats.last_sector = e.sector;
```

#### Envío al Daemon y Ajuste de Read-Ahead

La predicción recibida del daemon se mapea a un valor óptimo de `read_ahead_kb` y se aplica escribiendo directamente al sysfs del kernel (`/sys/block/sda/queue/read_ahead_kb`).

| Patrón Predicho | read_ahead_kb | Justificación                                                    |
| --------------- | ------------- | ---------------------------------------------------------------- |
| Sequential      | 256 KB        | Prefetch agresivo aprovecha accesos consecutivos.                |
| Random          | 16 KB         | Mínimo prefetch evita cargar datos innecesarios.                 |
| Mixed           | 64 KB         | Balance entre aprovechar secuencias cortas y evitar desperdicio. |

#### Servicio Systemd

El collector depende del daemon del ML para asegurar su disponibilidad:

```ini
[Unit]
Description=eBPF Block Trace Collector for Read-Ahead Optimization
After=ml-predictor.service
Requires=ml-predictor.service

[Service]
Type=simple
ExecStart=/usr/local/bin/ebpf_block_trace -d sda2 -w 2500
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

### 3.4 Flujo Completo de Ejecución

1. **Inicialización**:

   - El daemon carga el modelo y crea el Unix socket.
   - El collector inserta el programa eBPF y comienza a monitorear.

2. **Durante operación normal** (cada 2.5s):
   - eBPF captura eventos de I/O y los envía a userspace.
   - El Collector acumula estadísticas durante la ventana de 2.5s.
   - El Collector calcula las 5 features y las envía al Daemon por Unix Socket.
   - El Daemon normaliza, realiza la Inferencia (TorchScript) y retorna la clase predicha (ej: 0 = sequential).
   - El Collector mapea la predicción (0) al valor óptimo (256 KB).
   - Aplica el ajuste: `echo 256 > /sys/block/sda/queue/read_ahead_kb`.

---

## Conclusiones

Este proyecto demuestra la viabilidad de usar machine learning para optimización dinámica de parámetros del kernel de Linux. La integración de PyTorch con eBPF permite decisiones inteligentes en tiempo real con overhead mínimo, mejorando potencialmente el rendimiento del sistema según el patrón de carga de trabajo detectado.

### Beneficios Clave

- **Adaptación Dinámica**: El sistema se ajusta automáticamente según el comportamiento real del I/O.
- **Overhead Mínimo**: eBPF ejecuta en kernel space con impacto negligible.
- **Inferencia Rápida**: ~100-500 µs por predicción usando TorchScript.
- **Escalable**: Puede extenderse a otros parámetros del kernel.
