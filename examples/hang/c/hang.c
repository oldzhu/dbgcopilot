#include <pthread.h>
#include <stdio.h>
#include <unistd.h>

static pthread_mutex_t lock_a = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t lock_b = PTHREAD_MUTEX_INITIALIZER;

static void *worker_one(void *arg) {
    (void)arg;
    printf("worker_one acquiring lock_a\n");
    pthread_mutex_lock(&lock_a);
    sleep(1);
    printf("worker_one acquiring lock_b\n");
    pthread_mutex_lock(&lock_b);
    printf("worker_one acquired both locks\n");
    pthread_mutex_unlock(&lock_b);
    pthread_mutex_unlock(&lock_a);
    return NULL;
}

static void *worker_two(void *arg) {
    (void)arg;
    printf("worker_two acquiring lock_b\n");
    pthread_mutex_lock(&lock_b);
    sleep(1);
    printf("worker_two acquiring lock_a\n");
    pthread_mutex_lock(&lock_a);
    printf("worker_two acquired both locks\n");
    pthread_mutex_unlock(&lock_a);
    pthread_mutex_unlock(&lock_b);
    return NULL;
}

int main(void) {
    pthread_t t1;
    pthread_t t2;

    printf("Starting deadlock demo...\n");

    pthread_create(&t1, NULL, worker_one, NULL);
    pthread_create(&t2, NULL, worker_two, NULL);

    pthread_join(t1, NULL);
    pthread_join(t2, NULL);

    return 0;
}
