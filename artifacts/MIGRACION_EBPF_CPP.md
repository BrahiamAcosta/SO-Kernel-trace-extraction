# Migración de eBPF Block Trace a C++

## Resumen

Se ha migrado el script Python `ebpf_block_trace.py` a C++ (`ebpf_block_trace.cpp`) para unificar todo el stack tecnológico en un mismo lenguaje, mejorando el rendimiento y facilitando la integración.

## Cambios Realizados

### 1. Archivo Nuevo: `ebpf_block_trace.cpp`
- **Ubicación**: `artifacts/ebpf_block_trace.cpp`
- **Funcionalidad**: Recolecta estadísticas I/O usando eBPF y se comunica con el daemon ML predictor
- **Compatibilidad**: Mantiene la misma interfaz y protocolo que la versión Python

### 2. Makefile Actualizado
- Ahora compila tanto `ml_predictor.cpp` como `ebpf_block_trace.cpp`
- Incluye las dependencias de BCC para el collector eBPF
- Targets separados para cada binario

## Dependencias

### Para `ml_predictor`:
- **libtorch**: PyTorch C++ API
  - Ubicación: `$(HOME)/kml-project/libtorch`
  - Descargar desde: https://pytorch.org/get-started/locally/

### Para `ebpf_block_trace`:
- **BCC (BPF Compiler Collection)**: Framework para eBPF
  - Instalación en Ubuntu/Debian:
    ```bash
    sudo apt-get update
    sudo apt-get install -y bpfcc-tools libbpfcc-dev
    ```
  - O desde fuente: https://github.com/iovisor/bcc
  
- **Headers de BCC**: Normalmente en `/usr/include/bcc/`
  - Si están en otra ubicación, ajustar `BCC_PATH` en el Makefile

- **Permisos**: Requiere ejecución como root para usar eBPF

## Compilación

### Compilar Todo:
```bash
cd artifacts
make
```

### Compilar Solo el Daemon:
```bash
make ml_predictor
```

### Compilar Solo el Collector eBPF:
```bash
make ebpf_block_trace
```

### Limpiar:
```bash
make clean
```

## Uso

### 1. Iniciar el Daemon ML Predictor:
```bash
cd artifacts
./ml_predictor model_ts.pt
```

### 2. Iniciar el Collector eBPF (en otra terminal, como root):
```bash
cd artifacts
sudo ./ebpf_block_trace --device nvme0n1 --window 2500
```

### Opciones del Collector:
```
-d, --device DEVICE    Dispositivo block (default: nvme0n1)
-w, --window MS        Tamaño de ventana en ms (default: 2500)
-s, --sock PATH        Ruta al socket Unix (default: /tmp/ml_predictor.sock)
-h, --help             Mostrar ayuda
```

## Compatibilidad

### Protocolo de Comunicación
El collector C++ mantiene **exactamente el mismo protocolo** que la versión Python:

1. **Envío al daemon**: 5 floats (20 bytes) en little-endian
   - `[0]` Distancia promedio entre offsets (bytes)
   - `[1]` Variabilidad (jump ratio, 0.0-1.0)
   - `[2]` Tamaño promedio de I/O (bytes)
   - `[3]` Ratio secuencial (1 - jump_ratio, 0.0-1.0)
   - `[4]` IOPS (operaciones por segundo)

2. **Respuesta del daemon**: 1 int (4 bytes) con la clase predicha
   - `0` = sequential
   - `1` = random
   - `2` = mixed

3. **Escritura a sysfs**: Mismo mapeo de predicciones a readahead_kb
   - Sequential → 256 KB
   - Random → 16 KB
   - Mixed → 64 KB

### Características Calculadas
La lógica de cálculo de características es **idéntica** a la versión Python:
- Distancia promedio entre sectores consecutivos
- Ratio de saltos grandes (>1MB)
- Bandwidth calculado desde bytes acumulados
- IOPS calculado desde número de requests
- Tamaño promedio I/O = (bandwidth / IOPS)

## Ventajas de la Migración

1. **Unificación del Stack**: Todo en C++ facilita el mantenimiento
2. **Mejor Rendimiento**: C++ compilado es más eficiente que Python interpretado
3. **Menor Overhead**: Menos memoria y CPU que Python + BCC Python bindings
4. **Integración más Simple**: Mismo lenguaje que el daemon y el módulo del kernel

## Notas Importantes

### API de BCC C++
La API C++ de BCC puede variar según la versión instalada. Si encuentras errores de compilación:

1. **Verificar ubicación de headers**:
   ```bash
   find /usr -name "BPF.h" 2>/dev/null
   ```

2. **Ajustar BCC_PATH en Makefile** si los headers están en otra ubicación

3. **Verificar versión de BCC**:
   ```bash
   dpkg -l | grep bpfcc
   ```

### Alternativa si BCC C++ no está disponible
Si la API C++ de BCC no está disponible o es incompatible, puedes:
- Mantener la versión Python (`ebpf_block_trace.py`) como fallback
- Usar libbpf directamente (más moderno, pero requiere más código)
- Usar el script bash `ml_feature_collector.sh` que no requiere eBPF

## Troubleshooting

### Error: "No se encuentra BPF.h"
```bash
# Instalar headers de BCC
sudo apt-get install libbpfcc-dev

# O verificar ubicación
locate BPF.h
```

### Error: "Permission denied" al ejecutar
```bash
# El collector eBPF requiere root
sudo ./ebpf_block_trace
```

### Error: "Socket connection failed"
- Verificar que el daemon esté corriendo: `./ml_predictor model_ts.pt`
- Verificar que el socket exista: `ls -l /tmp/ml_predictor.sock`

### Error: "BPF program compilation failed"
- Verificar que el kernel tenga soporte para eBPF
- Verificar permisos de /sys/kernel/debug/tracing
- Probar con un kernel más reciente (5.8+)

## Archivos Relacionados

- `ml_predictor.cpp`: Daemon que recibe características y hace predicciones
- `ml_predictor.c`: Módulo del kernel para comunicación Netlink
- `ml_feature_collector.sh`: Alternativa bash que no requiere eBPF
- `ebpf_block_trace.py`: Versión Python original (puede mantenerse como fallback)

