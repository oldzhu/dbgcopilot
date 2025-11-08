CC ?= gcc
CFLAGS ?= -g -O0 -Wall -Wextra -pthread
BINDIR ?= ../../bin/c
TARGET := $(BINDIR)/hang

all: $(TARGET)

$(BINDIR):
	mkdir -p $(BINDIR)

$(TARGET): hang.c | $(BINDIR)
	$(CC) $(CFLAGS) -o $@ $<

clean:
	rm -f $(TARGET)

.PHONY: all clean
