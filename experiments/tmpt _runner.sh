#!/bin/bash
# ===============================
# VALIDACIÓN DEL PARÁMETRO
# ===============================
MODE="$1"   # baseline o ml

# ===============================
# CONFIGURACIÓN EXPERIMENTAL
# ===============================
REPEAT=3                          # repeticiones por configuración
FILESIZES=("100M" "500M" "1G")    # tamaños de archivo
ACCESS_TYPES=("seq" "rand" "mix") # tipos de acceso
BASE_DIR="./results_${MODE}"      # carpeta raíz depende del modo
DEVICE="./testfile"               # archivo sobre el cual leerá fio
BLOCK_DEVICE="sda"                # dispositivo de bloque para ajustar read_ahead

mkdir -p "$BASE_DIR"

# ===============================
# FUNCIÓN PARA EJECUTAR FIO
# ===============================
run_fio() {
    local access=$1  # seq / rand / mix
    local size=$2    # tamaño (100M, 500M...)
    local outdir=$3  # carpeta destino
    
    mkdir -p "$outdir"
    
    # Ajustar read_ahead según modo y tipo de acceso
    if [ "$MODE" == "ml" ]; then
        case $access in
            seq)  echo 256 > /sys/block/${BLOCK_DEVICE}/queue/read_ahead_kb ;;
            rand) echo 16 > /sys/block/${BLOCK_DEVICE}/queue/read_ahead_kb ;;
            mix)  echo 64 > /sys/block/${BLOCK_DEVICE}/queue/read_ahead_kb ;;
        esac
    else
        # Baseline: mantener valor fijo
        echo 128 > /sys/block/${BLOCK_DEVICE}/queue/read_ahead_kb
    fi

    # Leer y registrar el valor actual de read_ahead
    CURRENT_READAHEAD=$(cat /sys/block/${BLOCK_DEVICE}/queue/read_ahead_kb)
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    echo "$TIMESTAMP | $access | $size | $CURRENT_READAHEAD" >> "$READAHEAD_LOG"
    
    
    for (( r=1; r<=REPEAT; r++ )); do
        logfile="${outdir}/result_${size}_run${r}.json"
        case $access in
            seq)  RW="read" ;;
            rand) RW="randread" ;;
            mix)  RW="randrw" ;;
        esac
        fio --name=test \
            --filename="$DEVICE" \
            --rw=$RW \
            --filesize=$size \
            --bs=128k \
            --numjobs=1 \
            --iodepth=1 \
            --direct=1 \
            --time_based \
            --runtime=10 \
            --output-format=json \
            --output="$logfile"
    done
}

# ===============================
# EJECUCIÓN DEL EXPERIMENTO
# ===============================
echo "=== MODO: $MODE ==="
echo "Resultados en: $BASE_DIR"

for SIZE in "${FILESIZES[@]}"; do
    for ACCESS in "${ACCESS_TYPES[@]}"; do
        OUTDIR="${BASE_DIR}/${ACCESS}/${SIZE}"
        echo "=== Ejecutando $MODE | ACCESS=$ACCESS | SIZE=$SIZE ==="
        run_fio "$ACCESS" "$SIZE" "$OUTDIR"
    done
done

echo "=== Experimento completado para modo $MODE ==="
