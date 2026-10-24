// ISC. Native output-boundary tests for streaming Merkle construction.
#include "../proof/blake3_cpu.cpp"
#include <iostream>
#include <stdexcept>
static void require(bool b){if(!b)throw std::runtime_error("streaming Merkle guard/status failure");}
int main(){try{
 unsigned char key[32]={},tail[16]={},siblings[2080],root[64];
 std::memset(siblings,0xa5,sizeof(siblings));std::memset(root,0xa5,sizeof(root));
 uint64_t selected[]={0,3,6};size_t count=0;
 require(ph_constant_merkle(key,64,7,tail,16,selected,3,siblings+16,64,&count,root+16)==0);
 require(count<=64);
 for(unsigned i=0;i<16;++i)require(siblings[i]==0xa5&&siblings[sizeof(siblings)-1-i]==0xa5&&root[i]==0xa5&&root[sizeof(root)-1-i]==0xa5);
 require(ph_constant_merkle(key,64,7,tail,16,selected,3,siblings+16,0,&count,root+16)==2);
 require(ph_constant_merkle(key,64,8388609,tail,16,selected,3,siblings+16,64,&count,root+16)==1);
 uint64_t invalid[]={1,1};require(ph_constant_merkle(key,64,7,tail,16,invalid,2,siblings+16,64,&count,root+16)==1);
 std::cout<<"PASS: streaming Merkle CPU output guards and rejection bounds; GPU not run.\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
