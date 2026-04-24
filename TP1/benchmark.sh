#!/bin/bash
# Roda o benchmark da Parte 3: 10 execucoes por combinacao, calcula media
# Uso: bash benchmark.sh

make semaforos

N_VALS="1 10 100 1000"
COMBOS="1,1 1,2 1,4 1,8 2,1 4,1 8,1"
RUNS=10

echo "N,Np,Nc,tempo_medio" > results.csv

for N in $N_VALS; do
    for combo in $COMBOS; do
        Np=$(echo $combo | cut -d, -f1)
        Nc=$(echo $combo | cut -d, -f2)

        total=0
        for i in $(seq 1 $RUNS); do
            # ultima execucao salva o CSV de ocupacao; as outras nao (evita I/O no tempo)
            csv_flag=0
            [ $i -eq $RUNS ] && csv_flag=1
            t=$(./semaforos $N $Np $Nc $csv_flag 2>/dev/null)
            total=$(echo "$total + $t" | bc -l)
        done
        media=$(echo "scale=6; $total / $RUNS" | bc -l)

        echo "$N,$Np,$Nc,$media" >> results.csv
        echo "N=$N  Np=$Np  Nc=$Nc  media=${media}s"
    done
done

echo ""
echo "Resultados salvos em results.csv"
