#!/bin/bash

################################################################################
# CAPTURA DE DATASET - VERSIÓN CORREGIDA
################################################################################

set -e

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

PROJECT_DIR="$HOME/kml-project"
TRACES_DIR="$PROJECT_DIR/traces/training"
TEMP_DIR="/tmp/fio_tests"
SESSION_PREFIX="readahead_train"

FILE_SIZE="512M"         # Reducido para pruebas más rápidas
RUNTIME_PER_PATTERN=60   # 1 minuto por patrón (más rápido para debugging)
COOLDOWN=5

mkdir -p "$TRACES_DIR"/{sequential,random,mixed}
mkdir -p "$TEMP_DIR"

# ============================================================================
# FUNCIONES
# ============================================================================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

check_lttng() {
    log "Verificando LTTng..."
    
    # Verificar que lttng-sessiond esté corriendo
    if ! pgrep -x "lttng-sessiond" > /dev/null; then
        log "Iniciando lttng-sessiond..."
        sudo lttng-sessiond --daemonize
        sleep 2
    fi
    
    # Verificar módulos
    if ! lsmod | grep -q lttng_tracer; then
        log "ERROR: Módulos de LTTng no cargados"
        log "Ejecuta: sudo modprobe lttng-tracer"
        exit 1
    fi
    
    log "✓ LTTng verificado"
}

start_tracing() {
    local session_name=$1
    local output_dir=$2
    
    log "Iniciando sesión: $session_name"
    
    # Limpiar sesión anterior si existe
    lttng destroy "$session_name" 2>/dev/null || true
    
    # Crear sesión
    lttng create "$session_name" --output="$output_dir"
    
    # Habilitar TODOS los eventos del kernel (simplificado)
    log "  Habilitando eventos de kernel..."
    
    # Eventos de memoria
    lttng enable-event -k \
        'mm_*' \
        -s "$session_name" 2>/dev/null || {
        log "  ⚠ Algunos eventos mm_* no disponibles (OK)"
    }
    
    # Eventos de block
    lttng enable-event -k \
        'block_*' \
        -s "$session_name" 2>/dev/null || {
        log "  ⚠ Algunos eventos block_* no disponibles (OK)"
    }
    
    # Syscalls (método alternativo más compatible)
    lttng enable-event -k \
        --syscall \
        -a \
        -s "$session_name" 2>/dev/null || {
        log "  ⚠ No se pudieron habilitar syscalls (OK)"
    }
    
    # Iniciar tracing
    lttng start "$session_name"
    log "✓ Tracing activo"
}

stop_tracing() {
    local session_name=$1
    
    log "Deteniendo tracing: $session_name"
    lttng stop "$session_name" 2>/dev/null || true
    lttng destroy "$session_name" 2>/dev/null || true
    log "✓ Sesión cerrada"
}

run_fio_workload() {
    local pattern=$1
    local jobfile=$2
    
    log "Ejecutando carga: $pattern"
    
    fio "$jobfile" \
        --output="$TRACES_DIR/${pattern}/fio_output.txt" \
        2>&1 | tee "$TRACES_DIR/${pattern}/fio.log"
    
    log "✓ Carga completada"
}

convert_trace() {
    local pattern=$1
    local trace_dir="$TRACES_DIR/${pattern}/lttng_trace"
    local output_txt="$TRACES_DIR/${pattern}/trace_events.txt"
    
    log "Convirtiendo traza: $pattern"
    
    if [ ! -d "$trace_dir" ]; then
        log "  ERROR: Directorio de traza no existe: $trace_dir"
        return 1
    fi
    
    babeltrace "$trace_dir" > "$output_txt" 2>&1
    
    local event_count=$(wc -l < "$output_txt")
    local trace_size=$(du -sh "$trace_dir" | cut -f1)
    
    log "  ✓ Eventos: $event_count"
    log "  ✓ Tamaño: $trace_size"
    
    # Mostrar primeras líneas como muestra
    log "  Primeras líneas de la traza:"
    head -5 "$output_txt" | sed 's/^/    /'
}

cleanup() {
    log "Limpiando archivos temporales..."
    rm -rf "$TEMP_DIR"/*
    sync
}

# ============================================================================
# JOB FILES
# ============================================================================

create_sequential_job() {
    cat > /tmp/fio_sequential.job <<EOF
[global]
filename=$TEMP_DIR/test_sequential.dat
size=$FILE_SIZE
ioengine=sync
direct=0
time_based=1
runtime=$RUNTIME_PER_PATTERN
group_reporting=1

[sequential_read]
rw=read
bs=128k
numjobs=1
EOF
}

create_random_job() {
    cat > /tmp/fio_random.job <<EOF
[global]
filename=$TEMP_DIR/test_random.dat
size=$FILE_SIZE
ioengine=sync
direct=0
time_based=1
runtime=$RUNTIME_PER_PATTERN
group_reporting=1

[random_read]
rw=randread
bs=4k
numjobs=1
EOF
}

create_mixed_job() {
    cat > /tmp/fio_mixed.job <<EOF
[global]
filename=$TEMP_DIR/test_mixed.dat
size=$FILE_SIZE
ioengine=sync
direct=0
time_based=1
runtime=$RUNTIME_PER_PATTERN
group_reporting=1

[mixed_seq]
rw=read
bs=128k
numjobs=1
offset=0%
size=50%

[mixed_rand]
rw=randread
bs=4k
numjobs=1
offset=50%
size=50%
EOF
}

# ============================================================================
# MAIN
# ============================================================================

main() {
    log "========================================"
    log "CAPTURA DE DATASET (VERSIÓN CORREGIDA)"
    log "========================================"
    
    # Verificar permisos
    if [ "$EUID" -ne 0 ]; then
        log "ERROR: Ejecutar con sudo"
        exit 1
    fi
    
    # Verificar LTTng
    check_lttng
    
    # ========================================================================
    # PATRÓN SECUENCIAL
    # ========================================================================
    
    log ""
    log "========================================"
    log "FASE 1/3: CAPTURA SECUENCIAL"
    log "========================================"
    
    create_sequential_job
    cleanup
    
    start_tracing "${SESSION_PREFIX}_seq" "$TRACES_DIR/sequential/lttng_trace"
    sleep 2
    run_fio_workload "sequential" "/tmp/fio_sequential.job"
    sleep 1
    stop_tracing "${SESSION_PREFIX}_seq"
    
    convert_trace "sequential"
    
    sleep $COOLDOWN
    
    # ========================================================================
    # PATRÓN ALEATORIO
    # ========================================================================
    
    log ""
    log "========================================"
    log "FASE 2/3: CAPTURA ALEATORIA"
    log "========================================"
    
    create_random_job
    cleanup
    
    start_tracing "${SESSION_PREFIX}_rand" "$TRACES_DIR/random/lttng_trace"
    sleep 2
    run_fio_workload "random" "/tmp/fio_random.job"
    sleep 1
    stop_tracing "${SESSION_PREFIX}_rand"
    
    convert_trace "random"
    
    sleep $COOLDOWN
    
    # ========================================================================
    # PATRÓN MIXTO
    # ========================================================================
    
    log ""
    log "========================================"
    log "FASE 3/3: CAPTURA MIXTA"
    log "========================================"
    
    create_mixed_job
    cleanup
    
    start_tracing "${SESSION_PREFIX}_mixed" "$TRACES_DIR/mixed/lttng_trace"
    sleep 2
    run_fio_workload "mixed" "/tmp/fio_mixed.job"
    sleep 1
    stop_tracing "${SESSION_PREFIX}_mixed"
    
    convert_trace "mixed"
    
    # ========================================================================
    # RESUMEN
    # ========================================================================
    
    log ""
    log "========================================"
    log "CAPTURA COMPLETADA"
    log "========================================"
    log ""
    
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
    
    log "✓ Dataset capturado en: $TRACES_DIR"
    log ""
    log "Próximo paso:"
    log "  python3 consolidate_dataset.py"
}

main

log "✓ Script finalizado"