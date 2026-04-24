#!/bin/bash
# Testes do sistema P2P - TP2
# Uso: bash test.sh [block_size]
# Exemplo: bash test.sh 4096

BLOCK_SIZE=${1:-1024}
PYTHON=python3
PEER=./peer.py
LOG_DIR=logs
OUT_DIR=output

mkdir -p $LOG_DIR $OUT_DIR

# cores para saida
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; FAILED=$((FAILED+1)); }
info() { echo -e "${YELLOW}[INFO]${NC} $1"; }

FAILED=0

# ---------------------------------------------------------------
# Cria arquivos de teste com conteudo aleatorio
# ---------------------------------------------------------------
create_files() {
    info "Criando arquivos de teste..."
    dd if=/dev/urandom of=fileA_10k.bin  bs=1K   count=10  2>/dev/null
    dd if=/dev/urandom of=fileA_20k.bin  bs=1K   count=20  2>/dev/null
    dd if=/dev/urandom of=fileB_1m.bin   bs=1M   count=1   2>/dev/null
    dd if=/dev/urandom of=fileB_5m.bin   bs=1M   count=5   2>/dev/null
    dd if=/dev/urandom of=fileC_10m.bin  bs=1M   count=10  2>/dev/null
    info "Arquivos criados."
}

# ---------------------------------------------------------------
# Teste com 2 peers: seeder (porta 5000) + leecher (porta 5001)
# ---------------------------------------------------------------
run_test_2peers() {
    local FILE=$1
    local LABEL=$2
    local PORT_S=5000
    local PORT_L=5001

    info "--- Teste 2 peers | $LABEL | bloco=${BLOCK_SIZE}B ---"

    # gera metadados e encerra
    $PYTHON $PEER --meta-only --file $FILE --meta ${FILE}.meta.json \
        --block-size $BLOCK_SIZE > /dev/null 2>&1

    # inicia seeder em background
    $PYTHON $PEER --port $PORT_S --file $FILE --meta ${FILE}.meta.json \
        --block-size $BLOCK_SIZE > $LOG_DIR/seeder_${LABEL}.log 2>&1 &
    SEEDER_PID=$!
    sleep 0.5

    # inicia leecher e aguarda terminar
    $PYTHON $PEER --port $PORT_L --meta ${FILE}.meta.json \
        --neighbors 127.0.0.1:$PORT_S \
        --output $OUT_DIR > $LOG_DIR/leecher_${LABEL}.log 2>&1
    STATUS=$?

    kill $SEEDER_PID 2>/dev/null
    wait $SEEDER_PID 2>/dev/null

    if [ $STATUS -eq 0 ] && grep -q "sha256  : OK" $LOG_DIR/leecher_${LABEL}.log; then
        SPEED=$(grep "tempo" $LOG_DIR/leecher_${LABEL}.log | grep -oP '[0-9.]+ KB/s')
        pass "$LABEL  ($SPEED)"
    else
        fail "$LABEL"
        cat $LOG_DIR/leecher_${LABEL}.log
    fi
}

# ---------------------------------------------------------------
# Teste com 4 peers:
#   A (seeder, 5000) -> B (5001) -> C (5002)
#                    -> D (5003)
# B, C, D sao leechers; C e D podem receber de B tambem
# ---------------------------------------------------------------
run_test_4peers() {
    local FILE=$1
    local LABEL=$2

    info "--- Teste 4 peers | $LABEL | bloco=${BLOCK_SIZE}B ---"

    $PYTHON $PEER --meta-only --file $FILE --meta ${FILE}.meta.json \
        --block-size $BLOCK_SIZE > /dev/null 2>&1

    # peer A: seeder
    $PYTHON $PEER --port 5000 --file $FILE --meta ${FILE}.meta.json \
        --block-size $BLOCK_SIZE > $LOG_DIR/peerA_${LABEL}.log 2>&1 &
    PID_A=$!

    sleep 0.3

    # peer B: leecher de A
    $PYTHON $PEER --port 5001 --meta ${FILE}.meta.json \
        --neighbors 127.0.0.1:5000 \
        --output $OUT_DIR > $LOG_DIR/peerB_${LABEL}.log 2>&1 &
    PID_B=$!

    sleep 0.3

    # peer C: leecher de A e B
    $PYTHON $PEER --port 5002 --meta ${FILE}.meta.json \
        --neighbors 127.0.0.1:5000 127.0.0.1:5001 \
        --output $OUT_DIR > $LOG_DIR/peerC_${LABEL}.log 2>&1 &
    PID_C=$!

    # peer D: leecher de A e B
    $PYTHON $PEER --port 5003 --meta ${FILE}.meta.json \
        --neighbors 127.0.0.1:5000 127.0.0.1:5001 \
        --output $OUT_DIR > $LOG_DIR/peerD_${LABEL}.log 2>&1 &
    PID_D=$!

    # aguarda leechers terminarem
    wait $PID_B $PID_C $PID_D

    kill $PID_A 2>/dev/null
    wait $PID_A 2>/dev/null

    local ALL_OK=1
    for PEER_LOG in $LOG_DIR/peerB_${LABEL}.log $LOG_DIR/peerC_${LABEL}.log $LOG_DIR/peerD_${LABEL}.log; do
        if ! grep -q "sha256  : OK" $PEER_LOG 2>/dev/null; then
            ALL_OK=0
            fail "$LABEL ($(basename $PEER_LOG))"
        fi
    done

    [ $ALL_OK -eq 1 ] && pass "$LABEL (3 leechers)"
}

# ---------------------------------------------------------------
# Executa todos os testes
# ---------------------------------------------------------------
create_files

echo ""
echo "========================================"
echo " Testes com bloco = ${BLOCK_SIZE} bytes"
echo "========================================"

# File A - pequeno
run_test_2peers fileA_10k.bin "fileA_10k_2peers"
run_test_2peers fileA_20k.bin "fileA_20k_2peers"

# File B - medio
run_test_2peers fileB_1m.bin  "fileB_1m_2peers"
run_test_2peers fileB_5m.bin  "fileB_5m_2peers"

# File C - grande
run_test_2peers fileC_10m.bin "fileC_10m_2peers"

# 4 peers
run_test_4peers fileA_10k.bin "fileA_10k_4peers"
run_test_4peers fileB_1m.bin  "fileB_1m_4peers"

echo ""
echo "========================================"
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}Todos os testes passaram.${NC}"
else
    echo -e "${RED}$FAILED teste(s) falharam.${NC}"
fi
echo "========================================"
