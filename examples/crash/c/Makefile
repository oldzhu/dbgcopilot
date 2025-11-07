CC ?= gcc
CFLAGS ?= -g -O0 -Wall -Wextra

all: crash

crash: crash.c
	$(CC) $(CFLAGS) -o $@ $<

clean:
	rm -f crash

.PHONY: all clean
