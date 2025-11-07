package main

import "fmt"

func boom() {
	var ptr *int
	fmt.Println("About to dereference a nil pointer...")
	fmt.Println(*ptr)
}

func main() {
	fmt.Println("Go crash demo starting...")
	boom()
}
