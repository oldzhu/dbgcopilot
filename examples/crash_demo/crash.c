#include <stdio.h>
#include <stdlib.h>

static void boom(void) {
    int *p = NULL;
    *p = 42; // segfault
}

int main(int argc, char **argv) {
    printf("Crash demo starting...\n");
    boom();
    return 0;
}
