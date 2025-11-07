GO ?= go
BINDIR ?= ../../bin
TARGET := $(BINDIR)/hang

all: $(TARGET)

$(BINDIR):
	mkdir -p $(BINDIR)

$(TARGET): hang.go go.mod | $(BINDIR)
	$(GO) build -o $@ .

clean:
	rm -f $(TARGET)

.PHONY: all clean
