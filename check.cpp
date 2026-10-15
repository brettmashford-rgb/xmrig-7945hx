#include "crypto/randomx/aes_hash.hpp"
#include <cstdio>
#include <cstdint>
#include <vector>
int main() {
    for (size_t size : {size_t(16384), size_t(262144), size_t(1048576), size_t(2097152)}) {
        std::vector<uint8_t> pad(size);
        alignas(64) uint8_t hash[64], state[64];
        for (unsigned seed = 0; seed < 4; ++seed) {
            for (size_t i=0; i<size; ++i) pad[i] = uint8_t(i * 37 + (i >> 8) + seed * 59);
            for (size_t i=0; i<64; ++i) state[i] = uint8_t(i * 19 + seed * 7);
            for (int round=0; round<3; ++round) {
                hashAndFillAes1Rx4<0,2>(pad.data(),size,hash,state);
                fwrite(pad.data(),1,size,stdout);
                fwrite(hash,1,64,stdout);
                fwrite(state,1,64,stdout);
            }
        }
    }
}
