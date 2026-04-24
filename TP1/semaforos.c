/*
 * Produtor-Consumidor com Semaforos (Parte 3)
 * Compila: gcc -o semaforos semaforos.c -lpthread
 * Uso: ./semaforos <N> <Np> <Nc> [salvar_csv]
 *   N          = tamanho do buffer compartilhado
 *   Np         = numero de threads produtoras
 *   Nc         = numero de threads consumidoras
 *   salvar_csv = 1 salva CSV de ocupacao (default 0)
 */
#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>
#include <semaphore.h>
#include <time.h>

#define M 100000  /* total de numeros a consumir */

/* --- variaveis globais --- */
int N, Np, Nc;

int *buffer;
int buf_in  = 0;
int buf_out = 0;
int occ     = 0;   /* ocupacao atual do buffer */

int consumed_count = 0;
volatile int done  = 0;
int salvar_csv = 0;

/* acumula primos encontrados para evitar que o compilador elimine is_prime() */
volatile long long primos_encontrados = 0;

sem_t sem_empty;   /* slots vazios disponiveis */
sem_t sem_full;    /* slots cheios disponiveis */
pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;

/* log de ocupacao do buffer */
int *occ_log;
int  occ_idx = 0;

/* --- funcoes auxiliares --- */

int is_prime(int n) {
    if (n < 2) return 0;
    if (n == 2) return 1;
    if (n % 2 == 0) return 0;
    for (int i = 3; (long long)i * i <= n; i += 2)
        if (n % i == 0) return 0;
    return 1;
}

/* --- threads --- */

void *produtor(void *arg) {
    unsigned int seed = (unsigned int)(time(NULL) ^ (unsigned long)pthread_self());

    while (!done) {
        int num = rand_r(&seed) % 10000000 + 1;  /* [1, 10^7] */

        sem_wait(&sem_empty);
        if (done) {
            sem_post(&sem_empty);  /* libera para nao bloquear outro thread */
            break;
        }

        pthread_mutex_lock(&mutex);
        buffer[buf_in] = num;
        buf_in = (buf_in + 1) % N;
        occ++;
        if (occ_idx < M * 3) occ_log[occ_idx++] = occ;
        pthread_mutex_unlock(&mutex);

        sem_post(&sem_full);
    }

    return NULL;
}

void *consumidor(void *arg) {
    while (!done) {
        sem_wait(&sem_full);
        if (done) {
            sem_post(&sem_full);
            break;
        }

        pthread_mutex_lock(&mutex);
        int num = buffer[buf_out];
        buf_out = (buf_out + 1) % N;
        occ--;
        if (occ_idx < M * 3) occ_log[occ_idx++] = occ;
        consumed_count++;
        int parar = (consumed_count >= M);
        pthread_mutex_unlock(&mutex);

        sem_post(&sem_empty);

        /* verifica se e primo e imprime resultado (stderr para nao interferir no tempo medido) */
        int primo = is_prime(num);
        fprintf(stderr, "%d: %s\n", num, primo ? "primo" : "nao primo");
        if (primo) __sync_fetch_and_add(&primos_encontrados, 1);

        if (parar) {
            done = 1;
            /* acorda todas as threads possivelmente bloqueadas */
            for (int i = 0; i < Np; i++) sem_post(&sem_empty);
            for (int i = 0; i < Nc; i++) sem_post(&sem_full);
            break;
        }
    }

    return NULL;
}

/* --- main --- */

int main(int argc, char *argv[]) {
    if (argc < 4 || argc > 5) {
        fprintf(stderr, "Uso: %s <N> <Np> <Nc> [salvar_csv]\n", argv[0]);
        return 1;
    }

    N  = atoi(argv[1]);
    Np = atoi(argv[2]);
    Nc = atoi(argv[3]);
    if (argc == 5) salvar_csv = atoi(argv[4]);

    buffer  = malloc(N * sizeof(int));
    occ_log = malloc(M * 3 * sizeof(int));

    sem_init(&sem_empty, 0, N);  /* N slots vazios no inicio */
    sem_init(&sem_full,  0, 0);  /* 0 slots cheios no inicio */

    pthread_t *prod = malloc(Np * sizeof(pthread_t));
    pthread_t *cons = malloc(Nc * sizeof(pthread_t));

    struct timespec t_inicio, t_fim;
    clock_gettime(CLOCK_MONOTONIC, &t_inicio);

    for (int i = 0; i < Nc; i++) pthread_create(&cons[i], NULL, consumidor, NULL);
    for (int i = 0; i < Np; i++) pthread_create(&prod[i], NULL, produtor,   NULL);

    for (int i = 0; i < Np; i++) pthread_join(prod[i], NULL);
    for (int i = 0; i < Nc; i++) pthread_join(cons[i], NULL);

    clock_gettime(CLOCK_MONOTONIC, &t_fim);

    double elapsed = (t_fim.tv_sec  - t_inicio.tv_sec) +
                     (t_fim.tv_nsec - t_inicio.tv_nsec) / 1e9;

    printf("%.6f\n", elapsed);

    /* salva log de ocupacao apenas quando solicitado (./semaforos N Np Nc 1) */
    if (salvar_csv) {
        char nome[64];
        snprintf(nome, sizeof(nome), "occ_N%d_Np%d_Nc%d.csv", N, Np, Nc);
        FILE *f = fopen(nome, "w");
        if (f) {
            fprintf(f, "operacao,ocupacao\n");
            for (int i = 0; i < occ_idx; i++)
                fprintf(f, "%d,%d\n", i, occ_log[i]);
            fclose(f);
        }
    }

    sem_destroy(&sem_empty);
    sem_destroy(&sem_full);
    free(buffer);
    free(occ_log);
    free(prod);
    free(cons);

    return 0;
}
