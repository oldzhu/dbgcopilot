CARGO ?= cargo
BINDIR ?= ../../bin/rust
CRATE := rust_crash
TARGET := $(BINDIR)/crash
MANIFEST := Cargo.toml
SOURCES := $(shell find src -type f -name '*.rs')

all: $(TARGET)

$(BINDIR):
	mkdir -p $(BINDIR)

$(TARGET): $(MANIFEST) $(SOURCES) | $(BINDIR)
	@if ! command -v $(CARGO) >/dev/null 2>&1; then \
		echo "cargo not found; install Rust toolchain to build $@"; \
		exit 1; \
	fi
	RUSTFLAGS="-C remark=location -C debuginfo=2" $(CARGO) build --manifest-path $(MANIFEST)
	cp target/debug/$(CRATE) $@

clean:
	rm -f $(TARGET)
	@if command -v $(CARGO) >/dev/null 2>&1; then \
		$(CARGO) clean --manifest-path $(MANIFEST); \
	fi

.PHONY: all clean
