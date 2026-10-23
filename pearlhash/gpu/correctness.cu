// ISC license; see ../LICENSE. Correctness baseline, not a mining kernel.
extern "C" __global__ void cumulative(const int *a, const int *bt, int *out,
                                    unsigned rows, unsigned cols,
                                    unsigned k, unsigned rank) {
    unsigned pair = blockIdx.x * blockDim.x + threadIdx.x;
    if (pair >= rows * cols) return;
    unsigned u = pair / cols, v = pair % cols;
    int acc = 0;
    for (unsigned l = 0; l < k; ++l) {
        acc += a[u * k + l] * bt[v * k + l];
        if ((l + 1) % rank == 0)
            out[((l + 1) / rank - 1) * rows * cols + pair] = acc;
    }
}

extern "C" __global__ void transcript(const int *products, unsigned *words,
                                    unsigned pairs, unsigned steps) {
    // Separate launch supplies the global completion boundary.
    if (blockIdx.x || threadIdx.x) return;
    for (unsigned i = 0; i < 16; ++i) words[i] = 0;
    for (unsigned step = 0; step < steps; ++step) {
        unsigned folded = 0;
        for (unsigned p = 0; p < pairs; ++p)
            folded ^= (unsigned)products[step * pairs + p];
        unsigned slot = step % 16, old = words[slot];
        words[slot] = ((old << 13) | (old >> 19)) ^ folded;
    }
}
