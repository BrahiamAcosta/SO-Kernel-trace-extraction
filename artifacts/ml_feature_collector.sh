#!/bin/bash

DEVICE="/dev/sda5"

##########################################
# 1. OBTENER BW + IOPS usando tu iostat
##########################################
get_bw_iops() {
    # De tu iostat: columnas r/s, rKB/s, ..., w/s, wKB/s
    read r_s r_kbps _ _ _ _ w_s w_kbps <<< $(iostat -x 1 1 $DEVICE | awk "/^$(basename $DEVICE)/ {print \$4, \$5, \$10, \$11}")

    # IOPS
    IOPS_MEAN=$(awk -v r="$r_s" -v w="$w_s" 'BEGIN {print r + w}')

    # BW KB/s
    BW_KBPS=$(awk -v r="$r_kbps" -v w="$w_kbps" 'BEGIN {print r + w}')

    echo "$BW_KBPS" "$IOPS_MEAN"
}

##########################################
# 2. LATENCIA VIA perf (ns promedio)
##########################################
get_latency_ns() {
    LAT=$(sudo perf trace -e block:block_rq_complete 2>&1 | \
        awk '/duration/ {sum+=$NF; count++} END {if(count>0) print sum/count; else print 0}')
    echo "$LAT"
}

##########################################
# 3. SECTOR DISTANCE + JUMP RATIO
##########################################
get_sector_features() {
    sudo perf trace -e block:block_rq_issue 2>&1 | \
    awk '
    /sector=/ {
        split($0,a,"sector="); split(a[2],b," "); s=b[1]
        if(prev>0){
            d = s - prev
            if (d < 0) d = -d
            sum += d
            if (d > 10) jumps++
            count++
        }
        prev = s
    }
    END {
        if(count>0){
            print sum/count, jumps/count
        } else {
            print 0, 0
        }
    }'
}

##########################################
# 4. LOOP PRINCIPAL
##########################################
echo "ml_feature_collector: iniciando…"

while true; do
    # 1. sectores
    read AVG_SECTOR_DISTANCE SECTOR_JUMP_RATIO <<< $(get_sector_features)

    # → AQUI LA CORRECCIÓN: pasar sectores → BYTES
    AVG_SECTOR_DISTANCE_BYTES=$(awk -v s="$AVG_SECTOR_DISTANCE" 'BEGIN {print s * 512}')

    # 2. BW + IOPS
    read BW_KBPS IOPS_MEAN <<< $(get_bw_iops)

    # 3. Latencia ns
    LATENCY_NS=$(get_latency_ns)

    # 4. Features a enviar EXACTAMENTE como los usa el modelo
    FEATURES_STR="$AVG_SECTOR_DISTANCE_BYTES $SECTOR_JUMP_RATIO $BW_KBPS $LATENCY_NS $IOPS_MEAN"

    echo "Features: $FEATURES_STR"

    # 5. Enviar al daemon
    echo "$FEATURES_STR" > /run/ml_predictor.in

    # 6. Recibir predicción
    if read RESULT < /run/ml_predictor.out; then
        echo "Predicción del daemon: $RESULT"
    fi

    sleep 1
done
