// ISC license; see ../LICENSE. Offline GPU math harness; no network code.
#include <array>
#include <cstdint>
#include <cstring>
#include <dlfcn.h>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

using U = uint32_t;
static_assert(sizeof(int) == 4);
static void require(bool ok, const std::string &s) {
    if (!ok) throw std::runtime_error(s);
}
static U read_u32(std::istream &in) {
    unsigned char b[4];
    require(bool(in.read(reinterpret_cast<char*>(b), 4)), "truncated fixture");
    return U(b[0]) | U(b[1]) << 8 | U(b[2]) << 16 | U(b[3]) << 24;
}
struct Fixture {
    U rows, cols, k, rank;
    std::vector<int> a, bt, products;
    std::array<U,16> expected{}, words{};
    explicit Fixture(const char *path) {
        std::ifstream in(path, std::ios::binary);
        char magic[8];
        require(bool(in.read(magic, 8)) && !std::memcmp(magic,"PHGPU01\0",8), "bad fixture magic");
        rows=read_u32(in); cols=read_u32(in); k=read_u32(in); rank=read_u32(in);
        require(rows && rows<=32 && cols && cols<=32 && k && k<=65536 &&
                rank>=32 && rank<=1024 && !(rank & (rank-1)) && !(k%rank), "unsupported dimensions");
        a.resize(rows*k); bt.resize(cols*k);
        for (auto *v : {&a,&bt}) for (auto &x : *v) {
            U bits=read_u32(in);
            int64_t value = bits<=0x7fffffffU ? int64_t(bits) : int64_t(bits)-0x100000000LL;
            require(value>=-127 && value<=127, "noised value outside [-127,127]");
            x=int(value);
        }
        for (auto &x: expected) x=read_u32(in);
        require(in.peek()==std::char_traits<char>::eof(), "trailing fixture bytes");
        // Worst-case prefix bound avoids signed overflow on CPU and GPU.
        require(uint64_t(k)*127*127<=uint64_t(std::numeric_limits<int>::max()), "unsafe accumulation");
        U pairs=rows*cols, steps=k/rank;
        products.resize(size_t(pairs)*steps);
        std::vector<int64_t> acc(pairs);
        for (U step=0;step<steps;++step) {
            U fold=0;
            for (U u=0;u<rows;++u) for (U v=0;v<cols;++v) {
                U p=u*cols+v;
                for (U l=step*rank;l<(step+1)*rank;++l)
                    acc[p]+=int64_t(a[u*k+l])*bt[v*k+l];
                products[step*pairs+p]=int(acc[p]);
                fold^=U(acc[p]);
            }
            U &old=words[step%16]; old=((old<<13)|(old>>19))^fold;
        }
        require(words==expected, "CPU transcript differs from fixture");
    }
};

// CUDA driver ABI is loaded from the installed NVIDIA driver, not libcudart.
struct Driver {
    void *lib=nullptr, *ctx=nullptr, *module=nullptr;
    using Ptr=unsigned long long;
    std::vector<Ptr> allocations;
    template<class T> T sym(const char *name) {
        auto p=dlsym(lib,name); require(p!=nullptr,std::string("missing driver API ")+name);
        return reinterpret_cast<T>(p);
    }
    void check(int rc, const char *op) {
        if (rc) {
            const char *message=nullptr;
            auto get=reinterpret_cast<int(*)(int,const char**)>(dlsym(lib,"cuGetErrorString"));
            if (get) get(rc,&message);
            throw std::runtime_error(std::string(op)+": CUDA "+std::to_string(rc)+" "+(message?message:""));
        }
    }
    Driver()=default;
    Driver(const Driver&)=delete;
    ~Driver() {
        if (lib) {
            if (ctx) {
                auto free_mem=reinterpret_cast<int(*)(Ptr)>(dlsym(lib,"cuMemFree_v2"));
                auto unload=reinterpret_cast<int(*)(void*)>(dlsym(lib,"cuModuleUnload"));
                auto destroy=reinterpret_cast<int(*)(void*)>(dlsym(lib,"cuCtxDestroy_v2"));
                if(free_mem) for (auto p:allocations) free_mem(p);
                if(module && unload) unload(module);
                if(destroy) destroy(ctx);
            }
            dlclose(lib);
        }
    }
    void init(const char *cubin) {
        lib=dlopen("libcuda.so.1",RTLD_NOW|RTLD_LOCAL);
        require(lib!=nullptr,"libcuda.so.1 unavailable (use --cpu-only on a host without NVIDIA)");
        check(sym<int(*)(unsigned)>("cuInit")(0),"cuInit");
        int device,major,minor;
        check(sym<int(*)(int*,int)>("cuDeviceGet")(&device,0),"cuDeviceGet");
        auto attr=sym<int(*)(int*,int,int)>("cuDeviceGetAttribute");
        check(attr(&major,75,device),"compute major"); check(attr(&minor,76,device),"compute minor");
        char name[256]{};
        check(sym<int(*)(char*,int,int)>("cuDeviceGetName")(name,256,device),"device name");
        std::cout<<"GPU 0: "<<name<<" sm_"<<major<<minor<<"\n";
        require(major==12 && minor==0,"this checkpoint requires sm_120");
        check(sym<int(*)(void**,unsigned,int)>("cuCtxCreate_v2")(&ctx,0,device),"cuCtxCreate");
        check(sym<int(*)(void**,const char*)>("cuModuleLoad")(&module,cubin),"cuModuleLoad");
    }
    Ptr alloc(size_t size) {
        Ptr p; check(sym<int(*)(Ptr*,size_t)>("cuMemAlloc_v2")(&p,size),"cuMemAlloc");
        allocations.push_back(p); return p;
    }
    void upload(Ptr p, const void *src, size_t n) {
        check(sym<int(*)(Ptr,const void*,size_t)>("cuMemcpyHtoD_v2")(p,src,n),"upload");
    }
    void download(void *dst, Ptr p, size_t n) {
        check(sym<int(*)(void*,Ptr,size_t)>("cuMemcpyDtoH_v2")(dst,p,n),"download");
    }
    void launch(const char *name, U blocks, U threads, void **args) {
        void *fn;
        check(sym<int(*)(void**,void*,const char*)>("cuModuleGetFunction")(&fn,module,name),"get kernel");
        check(sym<int(*)(void*,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,
                        unsigned,void*,void**,void**)>("cuLaunchKernel")(
            fn,blocks,1,1,threads,1,1,0,nullptr,args,nullptr),name);
        check(sym<int(*)()>("cuCtxSynchronize")(),"kernel synchronize");
    }
    void run(Fixture &f) {
        auto a=alloc(f.a.size()*4), bt=alloc(f.bt.size()*4);
        auto products=alloc(f.products.size()*4), words=alloc(64);
        upload(a,f.a.data(),f.a.size()*4); upload(bt,f.bt.data(),f.bt.size()*4);
        // Poison outputs so partial kernel writes cannot pass silently.
        std::vector<U> poison(f.products.size(),0xdeadbeefU);
        std::array<U,16> word_poison; word_poison.fill(0xdeadbeefU);
        upload(products,poison.data(),poison.size()*4); upload(words,word_poison.data(),64);
        void *args[]={&a,&bt,&products,&f.rows,&f.cols,&f.k,&f.rank};
        U pairs=f.rows*f.cols, steps=f.k/f.rank;
        launch("cumulative",(pairs+127)/128,128,args);
        void *fold_args[]={&products,&words,&pairs,&steps};
        launch("transcript",1,1,fold_args);
        std::vector<int> result(f.products.size()); std::array<U,16> folded{};
        download(result.data(),products,result.size()*4); download(folded.data(),words,64);
        require(result==f.products,"GPU cumulative products differ from independent int64 CPU calculation");
        require(folded==f.expected,"GPU transcript differs from fixture");
    }
};

int main(int argc, char **argv) {
    try {
        bool cpu=argc>1 && std::string(argv[1])=="--cpu-only";
        require(argc>=3,"usage: pearl-gpu-check (--cpu-only | kernel.cubin) fixture.bin [...]");
        Driver driver;
        if (!cpu) driver.init(argv[1]);
        for (int i=2;i<argc;++i) {
            Fixture f(argv[i]); if(!cpu) driver.run(f);
            std::cout<<"PASS: "<<(cpu?"CPU input/transcript check: ":"GPU cumulative products + transcript: ")
                     <<argv[i]<<" ("<<f.rows<<"x"<<f.cols<<", k="<<f.k<<", rank="<<f.rank<<")\n";
        }
        std::cout<<"Offline math only; no GPU noise, digest, Merkle proof, pool client or pool verdict.\n";
        return 0;
    } catch (const std::exception &e) { std::cerr<<"FAIL: "<<e.what()<<"\n"; return 1; }
}
