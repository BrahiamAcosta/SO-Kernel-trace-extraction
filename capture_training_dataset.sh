#!/bin/bash

################################################################################
# CAPTURA DE DATASET PARA ENTRENAMIENTO DE MODELO READAHEAD
# Genera trazas etiquetadas de patrones: Sequential, Random, Mixed
################################################################################

set -e  # Salir si hay error

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

PROJECT_DIR="$HOME/kml-project"
TRACES_DIR="$PROJECT_DIR/traces/training"
TEMP_DIR="/tmp/fio_tests"
SESSION_PREFIX="readahead_train"

# Parámetros de captura
FILE_SIZE="1G"           # Tamaño de archivo de prueba
RUNTIME_PER_PATTERN=300  # 5 minutos por patrón (ajustar según necesidad)
COOLDOWN=10              # Segundos entre patrones

# Crear directorios
mkdir -p "$TRACES_DIR"/{sequential,random,mixed}
mkdir -p "$TEMP_DIR"

# ============================================================================
# FUNCIONES
# ============================================================================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

start_tracing() {
    local session_name=$1
    local output_dir=$2
    
    log "Iniciando sesión de tracing: $session_name"
    
    # Crear sesión
    lttng create "$session_name" --output="$output_dir"
    
    # Habilitar eventos de memoria/page cache
    lttng enable-event -k \
        mm_filemap_add_to_page_cache,\
        mm_filemap_delete_from_page_cache,\
        mm_vmscan_lru_shrink_inactive \
        -s "$session_name"
    
    # Eventos de block layer (readahead)
    lttng enable-event -k \
        block_rq_insert,\
        block_rq_issue,\
        block_rq_complete,\
        block_bio_frontmerge,\
        block_bio_backmerge \
        -s "$session_name"
    
    # Syscalls de lectura
    lttng enable-event -k --syscall \
        --name=read,pread64,readv,preadv,preadv2 \
        -s "$session_name"
    
    # Iniciar
    lttng start "$session_name"
    log "✓ Tracing activo"
}

stop_tracing() {
    local session_name=$1
    
    log "Deteniendo tracing: $session_name"
    lttng stop "$session_name" 2>/dev/null || true
    lttng destroy "$session_name" 2>/dev/null || true
    log "✓ Tracing detenido"
}

run_fio_workload() {
    local pattern=$1
    local jobfile=$2
    
    log "Ejecutando carga: $pattern"
    log "  Archivo de prueba: $TEMP_DIR/test_${pattern}.dat"
    log "  Duración: ${RUNTIME_PER_PATTERN}s"
    
    fio "$jobfile" \
        --output="$TRACES_DIR/${pattern}/fio_output.txt" \
        --output-format=normal,json \
        --write_bw_log="$TRACES_DIR/${pattern}/bw" \
        --write_lat_log="$TRACES_DIR/${pattern}/lat" \
        --write_iops_log="$TRACES_DIR/${pattern}/iops"
    
    log "✓ Carga completada: $pattern"
}

convert_trace() {
    local pattern=$1
    local trace_dir="$TRACES_DIR/${pattern}/lttng_trace"
    local output_txt="$TRACES_DIR/${pattern}/trace_events.txt"
    
    log "Convirtiendo traza a texto: $pattern"
    babeltrace "$trace_dir" > "$output_txt"
    
    local event_count=$(wc -l < "$output_txt")
    local trace_size=$(du -sh "$trace_dir" | cut -f1)
    
    log "  ✓ Eventos capturados: $event_count"
    log "  ✓ Tamaño de traza: $trace_size"
}

cleanup() {
    log "Limpiando archivos temporales..."
    rm -rf "$TEMP_DIR"/*
    sync
}

# ============================================================================
# WORKLOAD CONFIGURATIONS (FIO Job Files)
# ============================================================================

create_sequential_job() {
    cat > /tmp/fio_sequential.job <<EOF
[global]
filename=$TEMP_DIR/test_sequential.dat
size=$FILE_SIZE
ioengine=libaio
direct=1
time_based=1
runtime=$RUNTIME_PER_PATTERN
group_reporting=1

[sequential_read]
rw=read
bs=128k
numjobs=2
iodepth=4
EOF
}

create_random_job() {
    cat > /tmp/fio_random.job <<EOF
[global]
filename=$TEMP_DIR/test_random.dat
size=$FILE_SIZE
ioengine=libaio
direct=1
time_based=1
runtime=$RUNTIME_PER_PATTERN
group_reporting=1

[random_read]
rw=randread
bs=4k
numjobs=2
iodepth=16
EOF
}

create_mixed_job() {
    cat > /tmp/fio_mixed.job <<EOF
[global]
filename=$TEMP_DIR/test_mixed.dat
size=$FILE_SIZE
ioengine=libaio
direct=1
time_based=1
runtime=$RUNTIME_PER_PATTERN
group_reporting=1

[mixed_randrw]
rw=randrw
rwmixread=70
bs=64k
numjobs=2
iodepth=8

[mixed_sequential]
rw=read
bs=128k
numjobs=1
iodepth=4
offset=50%
EOF
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

main() {
    log "========================================"
    log "INICIO DE CAPTURA DE DATASET"
    log "========================================"
    log "Directorio de salida: $TRACES_DIR"
    log "Duración total estimada: $((RUNTIME_PER_PATTERN * 3 + COOLDOWN * 3)) segundos (~$(((RUNTIME_PER_PATTERN * 3 + COOLDOWN * 3) / 60)) minutos)"
    log ""
    
    # Verificar permisos
    if [ "$EUID" -ne 0 ]; then
        log "ERROR: Este script debe ejecutarse con sudo"
        exit 1
    fi
    
    # ========================================================================
    # 1. PATRÓN SECUENCIAL
    # ========================================================================
    
    log "========================================"
    log "FASE 1/3: CAPTURA SECUENCIAL"
    log "========================================"
    
    create_sequential_job
    cleanup
    
    start_tracing "${SESSION_PREFIX}_seq" "$TRACES_DIR/sequential/lttng_trace"
    sleep 2
    run_fio_workload "sequential" "/tmp/fio_sequential.job"
    stop_tracing "${SESSION_PREFIX}_seq"
    
    convert_trace "sequential"
    
    log "Cooldown de $COOLDOWN segundos..."
    sleep $COOLDOWN
    
    # ========================================================================
    # 2. PATRÓN ALEATORIO
    # ========================================================================
    
    log "========================================"
    log "FASE 2/3: CAPTURA ALEATORIA"
    log "========================================"
    
    create_random_job
    cleanup
    
    start_tracing "${SESSION_PREFIX}_rand" "$TRACES_DIR/random/lttng_trace"
    sleep 2
    run_fio_workload "random" "/tmp/fio_random.job"
    stop_tracing "${SESSION_PREFIX}_rand"
    
    convert_trace "random"
    
    log "Cooldown de $COOLDOWN segundos..."
    sleep $COOLDOWN
    
    # ========================================================================
    # 3. PATRÓN MIXTO
    # ========================================================================
    
    log "========================================"
    log "FASE 3/3: CAPTURA MIXTA"
    log "========================================"
    
    create_mixed_job
    cleanup
    
    start_tracing "${SESSION_PREFIX}_mixed" "$TRACES_DIR/mixed/lttng_trace"
    sleep 2
    run_fio_workload "mixed" "/tmp/fio_mixed.job"
    stop_tracing "${SESSION_PREFIX}_mixed"
    
    convert_trace "mixed"
    
    # ========================================================================
    # RESUMEN FINAL
    # ========================================================================
    
    log ""
    log "========================================"
    log "CAPTURA COMPLETADA"
    log "========================================"
    log ""
    log "Estadísticas del dataset:"
    echo ""
    
    for pattern in sequential random mixed; do
        trace_file="$TRACES_DIR/${pattern}/trace_events.txt"
        if [ -f "$trace_file" ]; then
            events=$(wc -l < "$trace_file")
            size=$(du -sh "$TRACES_DIR/${pattern}" | cut -f1)
            echo "  $pattern:"
            echo "    - Eventos: $events"
            echo "    - Tamaño: $size"
            echo ""
        fi
    done
    
    log "Todos los archivos en: $TRACES_DIR"
    log ""
    log "Próximo paso: Ejecutar script de consolidación"
    log "  $ python3 consolidate_dataset.py"
}

# Ejecutar
main

log "✓ Script finalizado exitosamente"