/*
 * Produtor-Consumidor com Pipes (Parte 2)
 * Compila: gcc -o pipes pipes.c
 * Uso: ./pipes <quantidade>
 */
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include <sys/wait.h>
#include <time.h>

#define MSG_SIZE 20

int is_prime(int n) {
    if (n < 2) return 0;
    if (n == 2) return 1;
    if (n % 2 == 0) return 0;
    for (int i = 3; i * i <= n; i += 2)
        if (n % i == 0) return 0;
    return 1;
}

int main(int argc, char *argv[]) {
    if (argc != 2) {
        fprintf(stderr, "Uso: %s <quantidade>\n", argv[0]);
        return 1;
    }

    int quantidade = atoi(argv[1]);
    int fd[2];

    if (pipe(fd) == -1) {
        perror("pipe");
        return 1;
    }

    pid_t pid = fork();
    if (pid == -1) {
        perror("fork");
        return 1;
    }

    if (pid == 0) {
        /* Filho: Consumidor - usa o read end do pipe */
        close(fd[1]);

        char buf[MSG_SIZE];
        while (read(fd[0], buf, MSG_SIZE) == MSG_SIZE) {
            int num = atoi(buf);
            if (num == 0) break;
            printf("%d: %s\n", num, is_prime(num) ? "primo" : "nao primo");
        }

        close(fd[0]);
        exit(0);
    } else {
        /* Pai: Produtor - usa o write end do pipe */
        close(fd[0]);

        srand(time(NULL));
        char buf[MSG_SIZE];
        int n = 1;

        for (int i = 0; i < quantidade; i++) {
            int delta = rand() % 100 + 1;  /* delta em [1, 100] */
            n += delta;
            memset(buf, 0, MSG_SIZE);
            snprintf(buf, MSG_SIZE, "%d", n);
            if (write(fd[1], buf, MSG_SIZE) < 0) { perror("write"); break; }
        }

        /* Envia 0 para sinalizar fim ao consumidor */
        memset(buf, 0, MSG_SIZE);
        snprintf(buf, MSG_SIZE, "0");
        if (write(fd[1], buf, MSG_SIZE) < 0) perror("write");

        close(fd[1]);
        wait(NULL);
        printf("Produtor: %d numeros enviados. Processo filho encerrado.\n", quantidade);
    }

    return 0;
}
