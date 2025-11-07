package main

import (
	"fmt"
	"sync"
	"time"
)

var (
	lockA sync.Mutex
	lockB sync.Mutex
)

func workerOne(wg *sync.WaitGroup) {
	defer wg.Done()
	fmt.Println("workerOne locking A")
	lockA.Lock()
	time.Sleep(500 * time.Millisecond)
	fmt.Println("workerOne locking B")
	lockB.Lock()
	fmt.Println("workerOne acquired both locks (unexpected)")
	lockB.Unlock()
	lockA.Unlock()
}

func workerTwo(wg *sync.WaitGroup) {
	defer wg.Done()
	fmt.Println("workerTwo locking B")
	lockB.Lock()
	time.Sleep(500 * time.Millisecond)
	fmt.Println("workerTwo locking A")
	lockA.Lock()
	fmt.Println("workerTwo acquired both locks (unexpected)")
	lockA.Unlock()
	lockB.Unlock()
}

func main() {
	var wg sync.WaitGroup

	fmt.Println("Go deadlock demo starting...")
	wg.Add(2)
	go workerOne(&wg)
	go workerTwo(&wg)
	wg.Wait()
}
