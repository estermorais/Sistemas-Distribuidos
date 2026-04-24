CC     = gcc
CFLAGS = -Wall -O2

all: pipes semaforos

pipes: pipes.c
	$(CC) $(CFLAGS) -o pipes pipes.c

semaforos: semaforos.c
	$(CC) $(CFLAGS) -o semaforos semaforos.c -lpthread

clean:
	rm -f pipes semaforos *.csv
