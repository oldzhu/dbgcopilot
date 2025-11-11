import time


def spin_forever() -> None:
    counter = 0
    while True:
        counter += 1
        if counter % 5_000_000 == 0:
            print(f"still spinning... {counter}")
        time.sleep(0.1)


if __name__ == "__main__":
    spin_forever()
