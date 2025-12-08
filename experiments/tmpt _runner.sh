#!/bin/bash
# ===============================
# VALIDACIÓN DEL PARÁMETRO
# ===============================
MODE="$1"   # baseline o ml

if [[ "$MODE" != "baseline" && "$MODE" != "ml" ]]; then
    echo "Error: Modo inválido. Uso: $0 {baseline|ml}"
    exit 1
fi

# ===============================
# CONFIGURACIÓN EXPERIMENTAL
# ===============================
REPEAT=3                          # repeticiones por configuración
FILESIZES=("100M" "500M" "1G")    # tamaños de archivo
ACCESS_TYPES=("seq" "rand" "mix") # tipos de acceso
BASE_DIR="./results_${MODE}"      # carpeta raíz depende del modo
DEVICE="./testfile"               # archivo sobre el cual leerá fio
BLOCK_DEVICE="sda"                # dispositivo de bloque real (cambiar según tu sistema)

mkdir -p "$BASE_DIR"

# ===============================
# CONFIGURACIÓN DE READ_AHEAD
# ===============================
# Valores óptimos por tipo de acceso (en KB)
declare -A READAHEAD_VALUES
READAHEAD_VALUES["seq"]=256   # Secuencial: alto para prefetching efectivo
READAHEAD_VALUES["rand"]=16   # Aleatorio: bajo para evitar desperdicio
READAHEAD_VALUES["mix"]=64    # Mixto: balance intermedio

# Guardar valor original de read_ahead_kb
ORIGINAL_READAHEAD=$(cat /sys/block/${BLOCK_DEVICE}/queue/read_ahead_kb 2>/dev/null)

# ===============================
# FUNCIÓN PARA CONFIGURAR READ_AHEAD
# ===============================
set_readahead() {
    local access_type=$1
    local value=${READAHEAD_VALUES[$access_type]}
    
    if [ "$MODE" == "baseline" ]; then
        # En modo baseline, usar valor fijo (el del sistema o un valor por defecto)
        value=128  # valor estándar/neutral
        echo "  [BASELINE] Manteniendo read_ahead_kb=$value (fijo)"
    else
        # En modo ml, ajustar según tipo de acceso
        echo "  [ML-OPTIMIZED] Configurando read_ahead_kb=$value para acceso $access_type"
    fi
    
    echo $value | sudo tee /sys/block/${BLOCK_DEVICE}/queue/read_ahead_kb > /dev/null
    
    # Verificar que se aplicó
    local current=$(cat /sys/block/${BLOCK_DEVICE}/queue/read_ahead_kb)
    if [ "$current" != "$value" ]; then
        echo "  WARNING: No se pudo configurar read_ahead_kb (current=$current, expected=$value)"
    fi
}

# ===============================
# FUNCIÓN PARA EJECUTAR FIO
# ===============================
run_fio() {
    local access=$1  # seq / rand / mix
    local size=$2    # tamaño (100M, 500M...)
    local outdir=$3  # carpeta destino
    
    mkdir -p "$outdir"
    
    # Configurar read_ahead según tipo de acceso y modo
    set_readahead "$access"
    
    # Guardar configuración usada en metadata
    local readahead=$(cat /sys/block/${BLOCK_DEVICE}/queue/read_ahead_kb)
    echo "read_ahead_kb=$readahead" > "${outdir}/config.txt"
    echo "mode=$MODE" >> "${outdir}/config.txt"
    echo "access_type=$access" >> "${outdir}/config.txt"
    echo "filesize=$size" >> "${outdir}/config.txt"
    
    for (( r=1; r<=REPEAT; r++ )); do
        logfile="${outdir}/result_${size}_run${r}.json"
        
        case $access in
            seq)  RW="read" ;;
            rand) RW="randread" ;;
            mix)  RW="randrw" ;;
        esac
        
        # Limpiar cache antes de cada ejecución para resultados consistentes
        sync
        echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null
        
        echo "    Ejecutando run $r/$REPEAT..."
        
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
            --output="$logfile" \
            2>/dev/null
    done
}

# ===============================
# RESTAURAR CONFIGURACIÓN AL SALIR
# ===============================
cleanup() {
    if [ -n "$ORIGINAL_READAHEAD" ]; then
        echo "Restaurando read_ahead_kb original: $ORIGINAL_READAHEAD"
        echo $ORIGINAL_READAHEAD | sudo tee /sys/block/${BLOCK_DEVICE}/queue/read_ahead_kb > /dev/null
    fi
}

trap cleanup EXIT INT TERM

# ===============================
# VERIFICACIÓN PREVIA
# ===============================
if [ ! -f "$DEVICE" ]; then
    echo "Creando archivo de prueba: $DEVICE"
    dd if=/dev/zero of="$DEVICE" bs=1M count=1024 2>/dev/null
fi

if [ ! -f /sys/block/${BLOCK_DEVICE}/queue/read_ahead_kb ]; then
    echo "ERROR: No se encuentra /sys/block/${BLOCK_DEVICE}/queue/read_ahead_kb"
    echo "Verifica que BLOCK_DEVICE esté configurado correctamente en el script"
    exit 1
fi

# ===============================
# EJECUCIÓN DEL EXPERIMENTO
# ===============================
echo "========================================"
echo "  EXPERIMENTO: $MODE"
echo "========================================"
echo "Resultados en: $BASE_DIR"
echo "Dispositivo: $BLOCK_DEVICE"
echo "Read_ahead original: $ORIGINAL_READAHEAD KB"
echo

START_TIME=$(date +%s)

for SIZE in "${FILESIZES[@]}"; do
    for ACCESS in "${ACCESS_TYPES[@]}"; do
        OUTDIR="${BASE_DIR}/${ACCESS}/${SIZE}"
        echo "=== Ejecutando $MODE | ACCESS=$ACCESS | SIZE=$SIZE ==="
        run_fio "$ACCESS" "$SIZE" "$OUTDIR"
        echo
    done
done

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo "========================================"
echo "  EXPERIMENTO COMPLETADO"
echo "========================================"
echo "Modo: $MODE"
echo "Duración total: ${DURATION}s"
echo "Resultados guardados en: $BASE_DIR"
echo

# ===============================
# GENERAR RESUMEN DE RESULTADOS
# ===============================
echo "Generando resumen de resultados..."

SUMMARY_FILE="${BASE_DIR}/summary.txt"
cat > "$SUMMARY_FILE" << EOF
========================================
RESUMEN DE EXPERIMENTO: $MODE
========================================
Fecha: $(date)
Duración: ${DURATION}s
Dispositivo: $BLOCK_DEVICE
Read_ahead original: $ORIGINAL_READAHEAD KB

CONFIGURACIONES PROBADAS:
EOF

for ACCESS in "${ACCESS_TYPES[@]}"; do
    RA_VALUE=${READAHEAD_VALUES[$ACCESS]}
    if [ "$MODE" == "baseline" ]; then
        RA_VALUE=128
    fi
    echo "  $ACCESS: read_ahead_kb=$RA_VALUE" >> "$SUMMARY_FILE"
done

echo "" >> "$SUMMARY_FILE"
echo "ESTRUCTURA DE RESULTADOS:" >> "$SUMMARY_FILE"
tree -L 3 "$BASE_DIR" >> "$SUMMARY_FILE" 2>/dev/null || ls -R "$BASE_DIR" >> "$SUMMARY_FILE"

echo "Resumen guardado en: $SUMMARY_FILE"
echo
echo "Para analizar los resultados:"
echo "  - Baseline:  ./results_baseline/"
echo "  - ML-tuned:  ./results_ml/"
echo "  - Comparar:  python3 analyze_results.py"
