GO ?= go
BINDIR ?= ../../bin
TARGET := $(BINDIR)/crash

all: $(TARGET)

$(BINDIR):
	mkdir -p $(BINDIR)

$(TARGET): crash.go go.mod | $(BINDIR)
	$(GO) build -o $@ .

clean:
	rm -f $(TARGET)

.PHONY: all clean
