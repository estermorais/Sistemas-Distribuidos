# TP2 — Transferência de Arquivos Peer-to-Peer

Sistema P2P onde cada peer atua simultaneamente como **servidor** (serve blocos que possui) e **cliente** (solicita blocos que faltam).

## Requisitos

```bash
python3  # versão 3.6+  (sem dependências externas)
```

## Estrutura dos arquivos

| Arquivo | Descrição |
|---|---|
| `peer.py` | Implementação completa do peer P2P |
| `test.sh` | Script de testes automatizados |
| `relatorio.pdf` | Relatório com decisões de projeto e resultados |

---

## Como usar

### Seeder (tem o arquivo)

```bash
python3 peer.py --port 5000 --file arquivo.bin --meta arquivo.meta.json --block-size 1024
```

Cria o arquivo de metadados `.json` e fica ouvindo na porta 5000.

### Leecher (quer baixar)

```bash
python3 peer.py --port 5001 --meta arquivo.meta.json --neighbors 127.0.0.1:5000
```

Conecta ao seeder, baixa todos os blocos, remonta o arquivo e verifica SHA-256.

### Múltiplos leechers (4 peers)

```bash
# Terminal 1 — seeder
python3 peer.py --port 5000 --file arquivo.bin --meta arquivo.meta.json

# Terminal 2 — leecher B (vizinho: A)
python3 peer.py --port 5001 --meta arquivo.meta.json --neighbors 127.0.0.1:5000 --output saida_B/

# Terminal 3 — leecher C (vizinhos: A e B)
python3 peer.py --port 5002 --meta arquivo.meta.json --neighbors 127.0.0.1:5000 127.0.0.1:5001 --output saida_C/

# Terminal 4 — leecher D (vizinhos: A e B)
python3 peer.py --port 5003 --meta arquivo.meta.json --neighbors 127.0.0.1:5000 127.0.0.1:5001 --output saida_D/
```

---

## Testes automatizados

```bash
# Bloco de 1024 bytes (padrão)
bash test.sh

# Bloco de 4096 bytes (variação)
bash test.sh 4096
```

O script cria os arquivos de teste, executa todos os cenários e verifica a integridade via SHA-256.

---

## Protocolo

Mensagens binárias com header de 12 bytes:

```
[ type (4B) | block_id (4B) | length (4B) | payload (length B) ]
```

| type | Significado |
|---|---|
| 1 | `REQUEST` — cliente solicita bloco |
| 2 | `DATA` — servidor envia dados do bloco |
| 3 | `NOHAVE` — servidor não tem o bloco |

O arquivo de metadados é um JSON com: `filename`, `file_size`, `block_size`, `total_blocks`, `sha256`.
