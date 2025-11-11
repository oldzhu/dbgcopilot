use std::thread;
use std::time::Duration;

fn main() {
    println!("Spinning forever to simulate a hang...");
    loop {
        thread::sleep(Duration::from_millis(100));
    }
}
