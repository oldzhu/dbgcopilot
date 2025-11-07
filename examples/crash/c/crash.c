#include <stdio.h>
#include <stdlib.h>

static void boom(void) {
    int *p = NULL;
    *p = 42; /* deliberate segmentation fault */
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;
    printf("Crash demo starting...\n");
    fflush(stdout);
    boom();
    return EXIT_SUCCESS;
}
