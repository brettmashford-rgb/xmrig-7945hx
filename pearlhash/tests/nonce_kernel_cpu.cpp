// ISC license. CPU execution of the nonce kernel body; never a GPU test.
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>
#define __global__
struct Index { unsigned x; } blockIdx{}, blockDim{128}, threadIdx{};
#include "../gpu/nonce_tail.cu"
static void require(bool ok,const char*msg){if(!ok)throw std::runtime_error(msg);}
static unsigned word(std::istream&in){unsigned char b[4];require(bool(in.read(reinterpret_cast<char*>(b),4)),"truncated fixture");return unsigned(b[0])|unsigned(b[1])<<8|unsigned(b[2])<<16|unsigned(b[3])<<24;}
int main(int argc,char**argv){
 try{
  require(argc==2,"usage: pearl-nonce-cpu-check fixture.bin");
  std::ifstream in(argv[1],std::ios::binary);char magic[8];require(bool(in.read(magic,8))&&std::string(magic,8)=="PHNONC01","invalid fixture magic");
  unsigned count=word(in);require(count>0&&count<=4096,"unsupported count");
  std::vector<unsigned> input(count*4),expected(count*4),output(count*4+8,0xa5a5a5a5U);
  for(auto&v:input)v=word(in);
  for(auto&v:expected)v=word(in);
  require(in.peek()==std::char_traits<char>::eof(),"trailing fixture data");
  for(blockIdx.x=0;blockIdx.x<(count+127)/128;++blockIdx.x)
   for(threadIdx.x=0;threadIdx.x<128;++threadIdx.x)nonce_tail(input.data(),output.data()+4,count);
  for(unsigned i=0;i<4;++i)require(output[i]==0xa5a5a5a5U&&output[output.size()-1-i]==0xa5a5a5a5U,"output guard changed");
  for(unsigned i=0;i<count*4;++i)require(output[i+4]==expected[i],"kernel body differs from CPU hash oracle");
  std::cout<<"PASS: CPU evaluation of nonce kernel body ("<<count<<" cases); output guards unchanged. GPU not run.\n";
  return 0;
 }catch(const std::exception&e){std::cerr<<"FAIL: "<<e.what()<<"\n";return 1;}
}
