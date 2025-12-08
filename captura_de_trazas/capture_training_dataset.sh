#!/bin/bash
################################################################################
# CAPTURA DE DATASET PARA ENTRENAMIENTO DE MODELO READAHEAD
# Genera trazas etiquetadas de patrones: Sequential, Random, Mixed
################################################################################
set -e

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

PROJECT_DIR="$HOME/kml-project"
TRACES_DIR="$PROJECT_DIR/traces/training"
TEMP_DIR="/tmp/fio_tests"
SESSION_PREFIX="readahead_train"

FILE_SIZE="2G"
RUNTIME_PER_PATTERN=120         # segundos por run
COOLDOWN=10                     # pausa entre runs
N_RUNS=3                        # repeticiones por patrón

mkdir -p "$TRACES_DIR"/{sequential,random,mixed}
mkdir -p "$TEMP_DIR"

# ============================================================================
# FUNCIONES
# ============================================================================

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

start_tracing() {
  local session_name=$1
  local output_dir=$2

  # Destruir si existe sesión previa
  if lttng list 2>/dev/null | grep -q "$session_name"; then
    lttng destroy "$session_name" 2>/dev/null || true
  fi

  # Crear nueva sesión
  lttng create "$session_name" --output="$output_dir" 2>/dev/null || {
    log "ERROR creando sesión LTTng: $session_name"
    return 1
  }

  # Obtener lista de eventos kernel disponibles
  mapfile -t ALL_EVENTS < <(lttng list -k 2>/dev/null | awk '{print $1}' | sort -u)

  # Patrones relevantes para I/O / readahead
  patterns=( "block" "bio" "filemap" "readahead" "page_cache" "pagecache" "mm_vmscan" "vfs_read" "generic_file_read_iter" "do_page_cache_readahead" )

  for pat in "${patterns[@]}"; do
    for ev in "${ALL_EVENTS[@]}"; do
      [[ "$ev" == *"$pat"* ]] && lttng enable-event -k "$ev" -s "$session_name" 2>/dev/null || true
    done
  done

  # Eventos comunes
  for ev in block_rq_insert block_rq_issue block_rq_complete block_bio_frontmerge block_bio_backmerge; do
    lttng enable-event -k "$ev" -s "$session_name" 2>/dev/null || true
  done

  # Syscalls lectura
  lttng enable-event -k --syscall --name=read,pread64,readv,preadv,preadv2 -s "$session_name" 2>/dev/null || true

  lttng start "$session_name" 2>/dev/null || {
    log "ERROR al iniciar tracing"
    return 1
  }

  log "✓ Tracing activo: $session_name"
}

stop_tracing() {
  local session_name=$1
  lttng stop "$session_name" 2>/dev/null || true
  lttng destroy "$session_name" 2>/dev/null || true
  log "✓ Tracing detenido"
}

cleanup() {
  log "Limpiando caché y archivos temporales..."
  sync; echo 3 > /proc/sys/vm/drop_caches
  rm -rf "$TEMP_DIR"/*
  sync
}

run_fio() {
  local pattern=$1
  local jobfile=$2
  local run_id=$3
  local mode=$4   # cold / warm

  local run_dir="$TRACES_DIR/$pattern/run_${run_id}_${mode}"
  mkdir -p "$run_dir"

  local session_name="${SESSION_PREFIX}_${pattern}_${run_id}_${mode}"

  log ">>> Run #$run_id ($pattern, $mode)"
  start_tracing "$session_name" "$run_dir/lttng_trace"
  sleep 2

  fio "$jobfile" \
    --output="$run_dir/fio_output.json" \
    --output-format=json \
    --write_bw_log="$run_dir/bw" \
    --write_lat_log="$run_dir/lat" \
    --write_iops_log="$run_dir/iops"

  stop_tracing "$session_name"

  babeltrace "$run_dir/lttng_trace" > "$run_dir/trace.txt" || log "WARN: babeltrace falló"
  local events=$(wc -l < "$run_dir/trace.txt" 2>/dev/null || echo 0)
  local size=$(du -sh "$run_dir/lttng_trace" | cut -f1)
  log "  ✓ Eventos capturados: $events | Tamaño: $size"

  # Guardar metadatos
  local meta_file="$TRACES_DIR/metadata.csv"
  if [ ! -f "$meta_file" ]; then
    echo "timestamp,pattern,run_id,mode,session_name,file_size,bs,iodepth,direct,numjobs,cpu_cores,mem_free_mb,trace_events,trace_size" > "$meta_file"
  fi

  local bs=$(grep -m1 "bs=" "$jobfile" | cut -d= -f2)
  local iodepth=$(grep -m1 "iodepth=" "$jobfile" | cut -d= -f2)
  local numjobs=$(grep -m1 "numjobs=" "$jobfile" | cut -d= -f2)
  local direct=$(grep -m1 "direct=" "$jobfile" | cut -d= -f2)
  local cpu_cores=$(nproc)
  local mem_free_mb=$(free -m | awk '/Mem:/ {print $4}')

  echo "$(date '+%Y-%m-%d_%H-%M-%S'),$pattern,$run_id,$mode,$session_name,$FILE_SIZE,$bs,$iodepth,$direct,$numjobs,$cpu_cores,$mem_free_mb,$events,$size" >> "$meta_file"

  log "  ✓ Metadatos registrados"
}

# ============================================================================
# JOB FILES
# ============================================================================

create_seq_job() {
  cat > /tmp/fio_seq.job <<EOF
[global]
filename=$TEMP_DIR/test_seq.dat
size=$FILE_SIZE
ioengine=libaio
time_based=1
runtime=$RUNTIME_PER_PATTERN
group_reporting=1
direct=1
numjobs=2
iodepth=4

[seqread]
rw=read
bs=128k
EOF
}

create_rand_job() {
  cat > /tmp/fio_rand.job <<EOF
[global]
filename=$TEMP_DIR/test_rand.dat
size=$FILE_SIZE
ioengine=libaio
time_based=1
runtime=$RUNTIME_PER_PATTERN
group_reporting=1
direct=1
numjobs=2
iodepth=16

[randread]
rw=randread
bs=4k
EOF
}

create_mix_job() {
  cat > /tmp/fio_mix.job <<EOF
[global]
filename=$TEMP_DIR/test_mix.dat
size=$FILE_SIZE
ioengine=libaio
time_based=1
runtime=$RUNTIME_PER_PATTERN
group_reporting=1
direct=1

[mixed]
rw=randrw
rwmixread=70
bs=64k
numjobs=2
iodepth=8
EOF
}

# ============================================================================
# MAIN
# ============================================================================

main() {
  log "========================================"
  log "INICIO DE CAPTURA DE DATASET"
  log "========================================"

  if [ "$EUID" -ne 0 ]; then
    log "ERROR: Ejecutar con sudo"
    exit 1
  fi

  for pattern in sequential random mixed; do
    log "====== Patrón: $pattern ======"

    case $pattern in
      sequential) create_seq_job; job=/tmp/fio_seq.job ;;
      random)     create_rand_job; job=/tmp/fio_rand.job ;;
      mixed)      create_mix_job; job=/tmp/fio_mix.job ;;
    esac

    for i in $(seq 1 $N_RUNS); do
      cleanup
      run_fio "$pattern" "$job" "$i" "cold"
      sleep $COOLDOWN

      run_fio "$pattern" "$job" "$i" "warm"
      sleep $COOLDOWN
    done
  done

  log "========================================"
  log "CAPTURA FINALIZADA"
  log "Dataset guardado en: $TRACES_DIR"
  log "========================================"
}

main
