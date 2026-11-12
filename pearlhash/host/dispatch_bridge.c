/* ISC. Bounded CUDA dispatch bridge. No CUDA headers, linking or kernel changes. */
#include <stddef.h>
#include <stdint.h>

typedef struct {
    void *func;
    unsigned gx,gy,gz,bx,by,bz,shared;
    void **params;
    void **extra;
} PHKernel;

typedef struct {
    uint64_t dst;
    size_t pitch;
    unsigned value,element_size;
    size_t width,height;
} PHMemset;

typedef int (*Reset)(uint64_t,unsigned,size_t,void *);
typedef int (*Launch)(void *,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,void *,void **,void **);
typedef int (*Sync)(void *);
typedef int (*Copy)(void *,uint64_t,size_t);
typedef int (*SetNode)(void *,void *,const PHKernel *);
typedef int (*GraphLaunch)(void *,void *);
typedef struct {Reset reset;Launch launch;Sync sync;Copy copy;SetNode set_node;GraphLaunch graph_launch;} PHApi;

typedef struct {
    uint64_t status,snapshot;
    void *host;
    size_t bytes;
    void *stream;
    PHKernel scanner,collector;
    void *executable,*scan_node,*collector_node;
    unsigned phase;
    uint64_t calls[6];
} PHCall;

size_t ph_abi_size(unsigned id){
    switch(id){case 0:return sizeof(PHApi);case 1:return sizeof(PHCall);case 2:return sizeof(PHKernel);case 3:return sizeof(PHMemset);default:return 0;}
}

#define RUN(stage,index,expr) do{call->phase=(stage);call->calls[index]++;int result=(expr);if(result)return result;}while(0)

int ph_dispatch(unsigned graph,const PHApi *api,PHCall *call){
    if(!api||!call)return -1;
    call->phase=0;
    if(graph>1||!api->sync||!api->copy||!call->stream||!call->host||!call->status||!call->snapshot||call->bytes!=504
       ||!call->scanner.func||!call->collector.func||!call->scanner.params||!call->collector.params
       ||!call->scanner.gx||call->scanner.gy!=1||call->scanner.gz!=1||call->scanner.bx!=256||call->scanner.by!=1||call->scanner.bz!=1
       ||!call->collector.gx||call->collector.bx!=128)return -2;
    if(graph){
        if(!api->set_node||!api->graph_launch||!call->executable||!call->scan_node||!call->collector_node)return -3;
        RUN(1,4,api->set_node(call->executable,call->scan_node,&call->scanner));
        RUN(2,4,api->set_node(call->executable,call->collector_node,&call->collector));
        RUN(3,5,api->graph_launch(call->executable,call->stream));
    }else{
        if(!api->reset||!api->launch)return -4;
        RUN(1,0,api->reset(call->status,0,2,call->stream));
        PHKernel *p=&call->scanner;
        RUN(2,1,api->launch(p->func,p->gx,p->gy,p->gz,p->bx,p->by,p->bz,p->shared,call->stream,p->params,p->extra));
        p=&call->collector;
        RUN(3,1,api->launch(p->func,p->gx,p->gy,p->gz,p->bx,p->by,p->bz,p->shared,call->stream,p->params,p->extra));
    }
    RUN(4,2,api->sync(call->stream));
    RUN(5,3,api->copy(call->host,call->snapshot,call->bytes));
    call->phase=6;return 0;
}
