# Trabalho Prático 1 — Sistemas Distribuídos

Implementação dos mecanismos de IPC: **Pipes** e **Produtor-Consumidor com Semáforos**.

---

## Estrutura dos arquivos

| Arquivo | Descrição |
|---|---|
| `pipes.c` | Produtor-Consumidor com anonymous pipes e `fork()` |
| `semaforos.c` | Produtor-Consumidor multithreaded com semáforos POSIX |
| `Makefile` | Compila os dois programas |
| `benchmark.sh` | Roda o estudo de caso da Produtor-Consumidor multithreaded com semáforos (10 execuções por combinação) |
| `plot.py` | Gera os gráficos de tempo médio e ocupação do buffer a partir dos CSVs |
| `gen_occ.py` | Gera os gráficos de ocupação para cenários específicos |
| `results.csv` | Tempos médios medidos no benchmark |
| `relatorio.pdf` | Relatório completo com decisões de projeto e análise dos resultados |

---

## Requisitos

> Os programas usam `fork()` e semáforos POSIX — precisam ser compilados no **Linux** (ou WSL no Windows).

```bash
sudo apt install gcc make bc python3-matplotlib python3-pandas
```

---

## Pipes

### Compilar e rodar

```bash
make pipes
./pipes <quantidade>
```

### Exemplo

```bash
./pipes 10
```

```
75: nao primo
151: primo
199: primo
281: primo
313: primo
411: nao primo
444: nao primo
463: primo
495: nao primo
521: primo
Produtor: 10 numeros enviados. Processo filho encerrado.
```

O programa cria um pipe, faz `fork()` e:
- **Pai (produtor):** gera números crescentes $N_i = N_{i-1} + \Delta$, $\Delta \in [1,100]$, e escreve no pipe em mensagens de 20 bytes
- **Filho (consumidor):** lê cada número, verifica se é primo e imprime o resultado; para ao receber o sentinela `0`

---

## Produtor-Consumidor com Semáforos

### Compilar e rodar

```bash
make semaforos
./semaforos <N> <Np> <Nc> [salvar_csv]
```

| Parâmetro | Descrição |
|---|---|
| `N` | Tamanho do buffer compartilhado |
| `Np` | Número de threads produtoras |
| `Nc` | Número de threads consumidoras |
| `salvar_csv` | `1` para salvar log de ocupação em CSV (opcional, padrão `0`) |

O programa imprime o tempo de execução em segundos e encerra após $M = 10^5$ números consumidos.

### Exemplos

```bash
./semaforos 10 2 2          # buffer=10, 2 produtores, 2 consumidores
./semaforos 1000 1 2 1      # buffer=1000, 1 produtor, 2 consumidores, salva CSV
```

### Estudo de caso completo

Roda todas as combinações do enunciado (10 execuções cada) e salva `results.csv`:

```bash
bash benchmark.sh
```

### Gerar gráficos

```bash
python3 plot.py      # gera tempo_medio.png e gráficos de ocupação
```

---

## Sincronização

Três primitivas são usadas:

- `sem_empty` (inicia em `N`): slots vazios disponíveis — produtor aguarda se buffer cheio
- `sem_full` (inicia em `0`): slots ocupados disponíveis — consumidor aguarda se buffer vazio
- `pthread_mutex`: exclusão mútua no acesso ao buffer circular
