def boom() -> None:
    p = None  # deliberately invalid dereference scenario
    print("About to blow up with a TypeError...")
    # This triggers an AttributeError to simulate a crash.
    p.upper()  # type: ignore[attr-defined]


if __name__ == "__main__":
    boom()
