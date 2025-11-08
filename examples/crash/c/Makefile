CC ?= gcc
CFLAGS ?= -g -O0 -Wall -Wextra
BINDIR ?= ../../bin/c
TARGET := $(BINDIR)/crash

all: $(TARGET)

$(BINDIR):
	mkdir -p $(BINDIR)

$(TARGET): crash.c | $(BINDIR)
	$(CC) $(CFLAGS) -o $@ $<

clean:
	rm -f $(TARGET)

.PHONY: all clean
