# Aggregate Makefile for building example programs.

.PHONY: all clean crash hang \
        crash-c crash-go crash-java crash-rust \
        hang-c hang-go hang-java hang-rust

all: crash hang

crash: crash-c crash-go crash-java crash-rust

hang: hang-c hang-go hang-java hang-rust

crash-c:
	$(MAKE) -C crash/c

crash-go:
	$(MAKE) -C crash/go

crash-java:
	$(MAKE) -C crash/java

crash-rust:
	$(MAKE) -C crash/rust

hang-c:
	$(MAKE) -C hang/c

hang-go:
	$(MAKE) -C hang/go

hang-java:
	$(MAKE) -C hang/java

hang-rust:
	$(MAKE) -C hang/rust

clean:
	$(MAKE) -C crash/c clean
	$(MAKE) -C crash/go clean
	$(MAKE) -C crash/java clean
	$(MAKE) -C crash/rust clean
	$(MAKE) -C hang/c clean
	$(MAKE) -C hang/go clean
	$(MAKE) -C hang/java clean
	$(MAKE) -C hang/rust clean

