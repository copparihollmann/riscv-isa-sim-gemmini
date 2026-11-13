#include "runtime.h"
typedef struct {
  const char *id,*parent,*family;
  unsigned group,before,in_offset,out_offset,mode,pattern,trial;
  uint64_t expected;
} case_t;
#include "cases.inc"
static uint8_t input_arena[8192] __attribute__((aligned(4096)));
static uint8_t output_arena[8192] __attribute__((aligned(4096)));
static volatile uint64_t request __attribute__((aligned(64)));
static volatile uint64_t complete __attribute__((aligned(64)));
static volatile uint64_t harts_vlenb[3] __attribute__((aligned(64)));
static struct { uint64_t start,end,instret,checksum,guards; } result __attribute__((aligned(64)));

#define VREGS "v0","v1","v2","v3","v4","v5","v6","v7","v8","v9","v10","v11","v12","v13","v14","v15","v16","v17","v18","v19","v20","v21","v22","v23","v24","v25","v26","v27","v28","v29","v30","v31"
#define LOADS(F) __asm__ volatile("vsetvli %0,zero,e8,m8,ta,ma\n\t" \
 "vle8.v v0,(%1)\n\t" F "add %1,%1,%0\n\t" \
 "vle8.v v8,(%1)\n\t" F "add %1,%1,%0\n\t" \
 "vle8.v v16,(%1)\n\t" F "add %1,%1,%0\n\t" \
 "vle8.v v24,(%1)\n\t" F : "=&r"(vl),"+&r"(cursor) :: "memory",VREGS)
#define STORES(F) __asm__ volatile("vsetvli %0,zero,e8,m8,ta,ma\n\t" \
 "vse8.v v0,(%1)\n\t" F "add %1,%1,%0\n\t" \
 "vse8.v v8,(%1)\n\t" F "add %1,%1,%0\n\t" \
 "vse8.v v16,(%1)\n\t" F "add %1,%1,%0\n\t" \
 "vse8.v v24,(%1)\n\t" F : "=&r"(vl),"+&r"(cursor) :: "memory",VREGS)

static void transport(const case_t *c) {
  uint8_t *in=input_arena+c->in_offset,*out=output_arena+c->out_offset,*cursor=in;
  unsigned long vl;
  uint64_t begin=cycles(),ret=retired();
  if(c->mode==2) { LOADS("fence rw,rw\n\t"); } else { LOADS(""); }
  if(c->mode!=0) {
    /* First lazy Zephyr restore closes with saved VL=0/vtype=0, then the
     * application requests32 e8/m1 elements. No scalar memory or breadcrumb
     * is inserted inside the four-load cursor block above. The app load
     * repeats the existing v8 bytes, preserving the full context golden. */
    __asm__ volatile("li t0,0\n\tvsetvl zero,t0,t0\n\tcsrw vstart,t0\n\tcsrw vcsr,t0\n\t"
      "vsetvli zero,%0,e8,m1,ta,ma\n\tvle8.v v8,(%1)"
      ::"r"(32UL),"r"(in+256):"t0","memory",VREGS);
  }
  cursor=out;
  if(c->mode==2) { STORES("fence rw,rw\n\t"); } else { STORES(""); }
  memory_fence();
  uint64_t endret=retired(),end=cycles(),sum=14695981039346656037ULL,guards=1;
  for(unsigned i=0;i<1024;++i)sum=(sum^out[i])*1099511628211ULL;
  for(unsigned i=1;i<=32;++i)if(out[-(int)i]!=0xa5||out[1023+i]!=0xa5)guards=0;
  result.start=begin;result.end=end;result.instret=endret-ret;result.checksum=sum;result.guards=guards;
}

static void print_region(const case_t *c) {
  putstr("IRIS_REGION {\"case_id\":\"");putstr(c->id);putstr("\",\"parent_case_id\":\"");putstr(c->parent);
  putstr("\",\"suite\":\"rvv_page_transport\",\"region\":\"kernel\",\"hart\":2,\"family\":\"");putstr(c->family);
  putstr("\",\"crossing_group\":");putuint(c->group);putstr(",\"bytes_before_page\":");putuint(c->before);
  putstr(",\"input_address\":");putuint((uintptr_t)input_arena+c->in_offset);
  putstr(",\"output_address\":");putuint((uintptr_t)output_arena+c->out_offset);
  putstr(",\"mode\":");putuint(c->mode);putstr(",\"pattern\":");putuint(c->pattern);putstr(",\"trial_id\":");putuint(c->trial);
  putstr(",\"start_cycle\":");putuint(result.start);putstr(",\"end_cycle\":");putuint(result.end);
  putstr(",\"instret_delta\":");putuint(result.instret);putstr(",\"checksum\":");putuint(result.checksum);
  putstr(",\"expected_checksum\":");putuint(c->expected);putstr(",\"guards_preserved\":");putstr(result.guards?"true":"false");
  putstr(",\"pass\":");putstr(result.checksum==c->expected&&result.guards?"true":"false");putstr("}\n");
}

void benchmark_main(unsigned hart) {
  unsigned long actual_vlenb;
  __asm__ volatile("csrr %0,vlenb":"=r"(actual_vlenb));
  harts_vlenb[hart]=actual_vlenb;
  barrier();
  if(hart==1)for(;;)__asm__ volatile("wfi");
  if(hart==2) {
    for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);++i) {
      while(__atomic_load_n(&request,__ATOMIC_ACQUIRE)!=i+1){}
      transport(&cases[i]);__atomic_store_n(&complete,i+1,__ATOMIC_RELEASE);
    }
    for(;;)__asm__ volatile("wfi");
  }
  putstr("IRIS_PAGE_HARTS {\"vlenb\":[");
  for(unsigned h=0;h<3;++h) {if(h)putstr(",");putuint(harts_vlenb[h]);}
  putstr("],\"expected\":32}\n");
  if(harts_vlenb[0]!=32||harts_vlenb[1]!=32||harts_vlenb[2]!=32) {
    putstr("IRIS_FATAL unexpected runtime VLEN\n");finish(1);
  }
  putstr("IRIS_PAGE_LAYOUT {\"input_arena\":");putuint((uintptr_t)input_arena);
  putstr(",\"output_arena\":");putuint((uintptr_t)output_arena);putstr(",\"arena_bytes\":8192,\"alignment\":4096}\n");
  unsigned failed=0;
  for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);++i) {
    const case_t *c=&cases[i];uint8_t *in=input_arena+c->in_offset,*out=output_arena+c->out_offset;
    for(unsigned group=0;group<4;++group)for(unsigned j=0;j<256;++j) {
      in[group*256+j]=c->pattern?(uint8_t)(j*17+group*61+13):0;out[group*256+j]=255;
    }
    for(unsigned j=1;j<=32;++j) {out[-(int)j]=0xa5;out[1023+j]=0xa5;}
    putstr("IRIS_PROBE_BEGIN {\"case_id\":\"");putstr(c->id);putstr("\",\"hart\":2}\n");
    uint64_t deadline=mtime()+250000;unsigned polls=0;
    __atomic_store_n(&request,i+1,__ATOMIC_RELEASE);
    while(__atomic_load_n(&complete,__ATOMIC_ACQUIRE)!=i+1) {
      if((++polls&1023)==0&&mtime()>deadline) {
        putstr("IRIS_PROBE_TIMEOUT {\"case_id\":\"");putstr(c->id);putstr("\",\"hart\":2}\n");finish(1);
      }
    }
    print_region(c);if(result.checksum!=c->expected||!result.guards)++failed;
  }
  putstr("IRIS_BATCH_DONE {\"failed\":");putuint(failed);putstr(",\"regions\":");putuint(sizeof(cases)/sizeof(cases[0]));putstr("}\n");finish(failed!=0);
}
