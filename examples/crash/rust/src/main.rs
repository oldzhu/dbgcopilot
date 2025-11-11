fn main() {
    crash();
}

fn crash() {
    let ptr: *mut i32 = std::ptr::null_mut();
    println!("About to dereference a null pointer... this will crash.");
    unsafe {
        *ptr = 42;
    }
}
