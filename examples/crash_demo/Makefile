CC=gcc
CFLAGS=-g -O0 -Wall

all: build

build: crash

crash: crash.c
	$(CC) $(CFLAGS) -o crash crash.c

run: crash
	./crash || true

clean:
	rm -f crash
