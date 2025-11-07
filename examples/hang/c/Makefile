CC ?= gcc
CFLAGS ?= -g -O0 -Wall -Wextra -pthread

all: hang

hang: hang.c
	$(CC) $(CFLAGS) -o $@ $<

clean:
	rm -f hang

.PHONY: all clean
