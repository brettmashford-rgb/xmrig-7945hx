// ISC license. Ordinary CPU evaluation of the GPU kernel body; GPU not run.
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>
#define __global__
struct Index {unsigned x;} blockIdx{},blockDim{128},threadIdx{};
#include "../gpu/chunk_commitment.cu"
static void require(bool ok,const char*msg){if(!ok)throw std::runtime_error(msg);}
static unsigned word(std::istream&in){unsigned char b[4];require(bool(in.read(reinterpret_cast<char*>(b),4)),"truncated fixture");return unsigned(b[0])|unsigned(b[1])<<8|unsigned(b[2])<<16|unsigned(b[3])<<24;}
int main(int argc,char**argv){try{
 require(argc==2,"usage: pearl-chunk-cpu-check fixture.bin");std::ifstream in(argv[1],std::ios::binary);char magic[8];require(bool(in.read(magic,8))&&std::string(magic,8)=="PHCHNK01","bad magic");unsigned batches=word(in),total=0;require(batches>0&&batches<=32,"invalid batch count");
 for(unsigned batch=0;batch<batches;++batch){unsigned long long first=word(in);first|=static_cast<unsigned long long>(word(in))<<32;unsigned count=word(in);require(count<=4096&&(!count||first<=~0ULL-(count-1)),"invalid chunk range");unsigned key[8];for(auto&v:key)v=word(in);std::vector<unsigned>input(count*256),expected(count*8),output(count*8+8,0xa5a5a5a5U);for(auto&v:input)v=word(in);for(auto&v:expected)v=word(in);
  for(blockIdx.x=0;blockIdx.x<(count?(count+127)/128:1);++blockIdx.x)for(threadIdx.x=0;threadIdx.x<128;++threadIdx.x)keyed_chunk_cvs(input.data(),key,first,count,output.data()+4);
  for(unsigned i=0;i<4;++i)require(output[i]==0xa5a5a5a5U&&output[output.size()-1-i]==0xa5a5a5a5U,"output guard changed");
  for(unsigned i=0;i<count*8;++i)require(output[i+4]==expected[i],"CPU kernel-body CV mismatch");
  total+=count;
 }
 require(in.peek()==std::char_traits<char>::eof(),"trailing data");std::cout<<"PASS: CPU kernel body: "<<total<<" chunk CVs, empty-launch case and guards. GPU not run.\n";return 0;
}catch(const std::exception&e){std::cerr<<"FAIL: "<<e.what()<<"\n";return 1;}}
