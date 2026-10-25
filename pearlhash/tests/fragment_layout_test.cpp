#include "fragment_layout.h"
#include <vector>
#include <cassert>
int main() {
    for(unsigned rows: {1U,10U,16U,80U,512U,2048U}) {
        std::vector<unsigned char> visited(rows*(32768/4),0);
        unsigned expected=0;
        for(unsigned base=0;base<32768;base+=16)
            for(unsigned row=0;row<rows;++row)
                for(unsigned byte=0;byte<16;byte+=4) {
                    unsigned actual=fragment_word_index(rows,row,base+byte);
                    assert(actual==expected++ && actual<visited.size());
                    assert(!visited[actual]++);
                }
        for(unsigned char count:visited)assert(count==1);
    }
    // One warp loading eight neighbouring rows at one 16-byte offset is contiguous.
    for(unsigned base: {0U,16U,32752U}) {
        unsigned first=fragment_word_index(80,8,base);
        for(unsigned lane=0;lane<32;++lane)
            assert(fragment_word_index(80,8+lane/4,base+(lane%4)*4)==first+lane);
    }
}
