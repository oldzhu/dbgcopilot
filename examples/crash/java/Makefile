JAVAC ?= javac
JAR ?= jar
JFLAGS ?= -g
BINDIR ?= ../../bin/java
JARDIR ?= ../../bin/jar
TARGET := $(BINDIR)/Crash.class
JARFILE := $(JARDIR)/Crash.jar
SOURCES := $(wildcard *.java)

all: $(TARGET) $(JARFILE)

$(BINDIR):
	mkdir -p $(BINDIR)

$(JARDIR):
	mkdir -p $(JARDIR)

$(TARGET): $(SOURCES) | $(BINDIR)
	@if ! command -v $(JAVAC) >/dev/null 2>&1; then \
		echo "javac not found; install a JDK to build $@"; \
		exit 1; \
	fi
	$(JAVAC) $(JFLAGS) -d $(BINDIR) $(SOURCES)

$(JARFILE): $(TARGET) | $(JARDIR)
	@if ! command -v $(JAR) >/dev/null 2>&1; then \
		echo "jar tool not found; install a JDK to build $@"; \
		exit 1; \
	fi
	$(JAR) cfe $(JARFILE) Crash -C $(BINDIR) .

clean:
	rm -f $(BINDIR)/Crash.class $(BINDIR)/Crash\$$*.class $(JARFILE)

.PHONY: all clean
