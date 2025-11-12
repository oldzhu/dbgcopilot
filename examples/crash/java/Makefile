JAVAC ?= javac
JFLAGS ?= -g
BINDIR ?= ../../bin/java
TARGET := $(BINDIR)/Crash.class
SOURCES := $(wildcard *.java)

all: $(TARGET)

$(BINDIR):
	mkdir -p $(BINDIR)

$(TARGET): $(SOURCES) | $(BINDIR)
	@if ! command -v $(JAVAC) >/dev/null 2>&1; then \
		echo "javac not found; install a JDK to build $@"; \
		exit 1; \
	fi
	$(JAVAC) $(JFLAGS) -d $(BINDIR) $(SOURCES)

clean:
	rm -f $(BINDIR)/Crash.class $(BINDIR)/Crash\$$*.class

.PHONY: all clean
