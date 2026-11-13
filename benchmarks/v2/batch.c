#include "runtime.h"
#include "vme.h"

enum { K_dependent,K_independent,K_frontend,K_branch,K_memory,K_atomic,
       K_scalar_fp,K_vector_int,K_vector_fp,K_vme_int,K_vme_fp8,
       K_row_read,K_row_write,K_tile_zero,K_vme_memory,K_shared_fpu,
       K_pipeline,K_pipeline_vme,K_vme_refusal };
typedef struct { const char *id; unsigned kind,n,mask,sew,lmul,mode,bytes,protocol,edge,tk,tiles; uint64_t expected[3]; } case_t;
#include "cases.inc"
typedef struct __attribute__((aligned(64))) { uint64_t start,end,instret,checksum; } result_t;
typedef struct __attribute__((aligned(64))) { uint64_t value; } counter_t;
static result_t results[3];
static uint32_t data[3][262144] __attribute__((aligned(64)));
static uint32_t shared_data[262144] __attribute__((aligned(64)));
static uint32_t eviction[3][524288] __attribute__((aligned(64)));
static uint64_t output[3][64] __attribute__((aligned(64)));
static uint8_t matrix_a[3][32] __attribute__((aligned(64))),matrix_b[3][32] __attribute__((aligned(64)));
static volatile uint64_t scratch_sink[3],scalar_saved[3];
static unsigned vl_saved[3],done,complete,failed;
static uint64_t shared_counter __attribute__((aligned(64))),false_shared[3] __attribute__((aligned(64)));
static counter_t separated[3];
static unsigned pipeline_stage __attribute__((aligned(64)));
static uint32_t pipeline_input[8] __attribute__((aligned(64))),pipeline_output[32] __attribute__((aligned(64)));
static uint8_t pipeline_a[32] __attribute__((aligned(64))),pipeline_b[32] __attribute__((aligned(64)));

static unsigned active_count(unsigned mask) { return (mask&1)+((mask>>1)&1)+((mask>>2)&1); }
static uint64_t dependent(unsigned n) {
  uint64_t x=1;
  for(unsigned i=0;i<n;++i) __asm__ volatile("addi %0,%0,1\n\taddi %0,%0,1\n\taddi %0,%0,1\n\taddi %0,%0,1\n\taddi %0,%0,1\n\taddi %0,%0,1\n\taddi %0,%0,1\n\taddi %0,%0,1":"+r"(x));
  return x;
}
static uint64_t independent(unsigned n) {
  uint64_t a=1,b=2,c=3,d=4,e=5,f=6,g=7,h=8;
  for(unsigned i=0;i<n;++i) __asm__ volatile("addi %0,%0,1\n\taddi %1,%1,1\n\taddi %2,%2,1\n\taddi %3,%3,1\n\taddi %4,%4,1\n\taddi %5,%5,1\n\taddi %6,%6,1\n\taddi %7,%7,1"
    :"+r"(a),"+r"(b),"+r"(c),"+r"(d),"+r"(e),"+r"(f),"+r"(g),"+r"(h));
  return a+b+c+d+e+f+g+h;
}
#define FRONTEND(BYTES) \
static __attribute__((noinline,aligned(64))) uint64_t frontend_##BYTES(uint64_t x) { \
  __asm__ volatile(".option push\n\t.option norvc\n\t.rept " #BYTES "/4\n\taddi %0,%0,1\n\t.endr\n\t.option pop":"+r"(x)); return x; }
FRONTEND(512)
FRONTEND(4096)
FRONTEND(16384)
static uint64_t frontend(unsigned bytes,unsigned n) {
  uint64_t x=0; for(unsigned i=0;i<n;++i) {
    if(bytes==512) x=frontend_512(x); else if(bytes==4096) x=frontend_4096(x); else x=frontend_16384(x);
  } return x;
}
static uint64_t branches(const case_t *c) {
  uint32_t state=1; uint64_t total=0;
  for(unsigned i=0;i<c->n;++i) {
    state=(state>>1)^((0U-(state&1U))&0xd0000001U);
    unsigned test=c->mode?(state&1):0;
    __asm__ volatile("beqz %1,1f\n\taddi %0,%0,3\n\tj 2f\n1:\taddi %0,%0,1\n2:":"+r"(total):"r"(test));
  } return total;
}
static uint64_t sum_bits(unsigned h,unsigned count,unsigned sew,unsigned offset) {
  uint64_t sum=0; const uint8_t *p=(const uint8_t *)output[h]+offset;
  if(sew==8) for(unsigned i=0;i<count;++i) sum+=p[i];
  if(sew==16) for(unsigned i=0;i<count;++i) sum+=((const uint16_t *)p)[i];
  if(sew==32) for(unsigned i=0;i<count;++i) sum+=((const uint32_t *)p)[i];
  if(sew==64) for(unsigned i=0;i<count;++i) sum+=((const uint64_t *)p)[i];
  return sum;
}
#define SETV(SEW,LMUL) case SEW*8+LMUL: __asm__ volatile("vsetvli %0,%1,e" #SEW ",m" #LMUL ",ta,ma":"=r"(vl):"r"(avl):"memory"); break
static void vector_setup(unsigned h,unsigned sew,unsigned lmul,unsigned fp) {
  unsigned long vl=0,avl=(unsigned long)-1;
  switch(sew*8+lmul) {
    SETV(8,1); SETV(8,2); SETV(8,4); SETV(16,1); SETV(16,2); SETV(16,4);
    SETV(32,1); SETV(32,2); SETV(32,4); SETV(64,1); SETV(64,2); SETV(64,4);
  }
  vl_saved[h]=vl;
  uint64_t one=fp?(sew==16?0x3c00:sew==32?0x3f800000:0x3ff0000000000000ULL):1;
  uint64_t initial=fp?0:1;
  __asm__ volatile("vmv.v.x v8,%0\n\tvmv.v.x v16,%1\n\tvmv.v.x v24,%0\n\tvmv.v.x v28,%1"::"r"(initial),"r"(one):"memory");
}
#define VSTORE(SEW,REG,PTR) __asm__ volatile("vse" #SEW ".v " #REG ",(%0)"::"r"(PTR):"memory")
static void vector_drain(unsigned h,const case_t *c) {
  void *p=output[h];
  if(c->sew==8) { VSTORE(8,v8,p); if(c->mode) { p=(uint8_t *)p+vl_saved[h]; VSTORE(8,v24,p); } }
  if(c->sew==16) { VSTORE(16,v8,p); if(c->kind==K_vector_int&&c->mode) { p=(uint8_t *)p+2*vl_saved[h]; VSTORE(16,v24,p); } }
  if(c->sew==32) { VSTORE(32,v8,p); if(c->kind==K_vector_int&&c->mode) { p=(uint8_t *)p+4*vl_saved[h]; VSTORE(32,v24,p); } }
  if(c->sew==64) { VSTORE(64,v8,p); if(c->kind==K_vector_int&&c->mode) { p=(uint8_t *)p+8*vl_saved[h]; VSTORE(64,v24,p); } }
}
static void scalar_setup(unsigned sew) {
  uint64_t one=sew==16?0x3c00:sew==32?0x3f800000:0x3ff0000000000000ULL;
  if(sew==16) __asm__ volatile("fmv.h.x ft0,zero\n\tfmv.h.x ft1,%0"::"r"(one):"ft0","ft1");
  if(sew==32) __asm__ volatile("fmv.w.x ft0,zero\n\tfmv.w.x ft1,%0"::"r"(one):"ft0","ft1");
  if(sew==64) __asm__ volatile("fmv.d.x ft0,zero\n\tfmv.d.x ft1,%0"::"r"(one):"ft0","ft1");
}
static void scalar_add(unsigned sew) {
  if(sew==16) __asm__ volatile("fadd.h ft0,ft0,ft1":::"ft0");
  if(sew==32) __asm__ volatile("fadd.s ft0,ft0,ft1":::"ft0");
  if(sew==64) __asm__ volatile("fadd.d ft0,ft0,ft1":::"ft0");
}
static uint64_t scalar_bits(unsigned sew) {
  uint64_t out;
  if(sew==16) { __asm__ volatile("fmv.x.h %0,ft0":"=r"(out)); return out&0xffff; }
  if(sew==32) { __asm__ volatile("fmv.x.w %0,ft0":"=r"(out)); return out&0xffffffff; }
  __asm__ volatile("fmv.x.d %0,ft0":"=r"(out)); return out;
}
static void matrix_mac(const case_t *c) {
  if(c->kind==K_vme_fp8) {
    if(c->mode&1) VME_MM_E5_E4(0,8,16); else VME_MM_E4_E4(0,8,16);
  } else {
    VME_MM_U_U(0,8,16);
    if(c->tiles==4) { VME_MM_U_U(1,8,16); VME_MM_U_U(2,8,16); VME_MM_U_U(3,8,16); }
  }
}
static void matrix_setup(unsigned h,const case_t *c) {
  unsigned a=c->kind==K_vme_fp8?((c->mode&1)?0x3c:0x38):1;
  unsigned b=c->kind==K_vme_fp8?((c->mode&2)?0x3c:0x38):1;
  for(unsigned i=0;i<32;++i) { matrix_a[h][i]=a; matrix_b[h][i]=b; }
  if(c->kind==K_vme_fp8&&(c->mode&2)) vme_vsettnt_e8w4_alt(c->edge); else vme_vsettnt_e8w4(c->edge);
  vme_vsettm(c->edge); vme_vsettk(c->tk);
  VME_VTZERO(0); if(c->tiles==4) { VME_VTZERO(1); VME_VTZERO(2); VME_VTZERO(3); }
  __asm__ volatile("vle8.v v8,(%0)\n\tvle8.v v10,(%0)\n\tvle8.v v12,(%0)\n\tvle8.v v14,(%0)\n\tvle8.v v16,(%1)\n\tvle8.v v18,(%1)\n\tvle8.v v20,(%1)\n\tvle8.v v22,(%1)"::"r"(matrix_a[h]),"r"(matrix_b[h]):"memory");
  if(c->kind==K_row_read||c->kind==K_tile_zero) for(unsigned i=0;i<7;++i) VME_MM_U_U(0,8,16);
  if(c->kind==K_row_read||c->kind==K_row_write) {
    vme_vsettnt_e32w1(c->edge); vme_vsettm(c->edge);
    if(c->kind==K_row_write) { VME_VTZERO(0); __asm__ volatile("vmv.v.i v24,7":::"memory"); }
  }
}
static void matrix_drain(unsigned h,const case_t *c) {
  vme_vsettnt_e32w1(c->edge);
  unsigned row=c->kind==K_row_write?(c->n-1)&31:0;
  VME_VTMV_V_T(24,vme_tss(0,VME_TSS_ROW,row)); VSTORE(32,v24,output[h]);
  if(c->tiles==4) {
    VME_VTMV_V_T(24,vme_tss(1,VME_TSS_ROW,0)); VSTORE(32,v24,(uint32_t *)output[h]+32);
    VME_VTMV_V_T(24,vme_tss(2,VME_TSS_ROW,0)); VSTORE(32,v24,(uint32_t *)output[h]+64);
    VME_VTMV_V_T(24,vme_tss(3,VME_TSS_ROW,0)); VSTORE(32,v24,(uint32_t *)output[h]+96);
  }
}
static void prepare(unsigned h,const case_t *c) {
  scalar_saved[h]=0;
  if(c->kind==K_frontend) scratch_sink[h]=frontend(c->bytes,1);
  if(c->kind==K_memory||c->kind==K_vme_memory) {
    volatile uint32_t *p=data[h]; unsigned words=c->bytes/4;
    if(c->kind==K_memory&&c->mode==2) p=shared_data;
    else for(unsigned i=0;i<words;++i) p[i]=(c->kind==K_memory&&c->mode==1)?((i+16)%words):1;
    uint64_t sink=0;
    if(c->protocol==1) { for(unsigned i=0;i<words;++i) sink+=p[i]; }
    if(c->protocol==2) { volatile uint32_t *e=eviction[h]; for(unsigned i=0;i<524288;i+=16) sink+=e[i]; }
    scratch_sink[h]=sink;
    if(c->kind==K_memory&&c->mode==4&&h==2) vector_setup(h,32,1,0);
  }
  if(c->kind==K_scalar_fp) scalar_setup(c->sew);
  if(c->kind==K_vector_int||c->kind==K_vector_fp) vector_setup(h,c->sew,c->lmul,c->kind==K_vector_fp);
  if(c->kind>=K_vme_int&&c->kind<=K_vme_memory) matrix_setup(h,c);
  if(c->kind==K_shared_fpu) { scalar_setup(32); vector_setup(h,32,1,1); }
  if(c->kind==K_pipeline&&h==(c->mode+1)%3) vector_setup(h,32,1,0);
  if(c->kind==K_pipeline_vme&&h==c->mode) matrix_setup(h,c);
  memory_fence();
}
static uint64_t kernel(unsigned h,const case_t *c) {
  if(c->kind==K_dependent) return dependent(c->n);
  if(c->kind==K_independent) return independent(c->n);
  if(c->kind==K_frontend) return frontend(c->bytes,c->n);
  if(c->kind==K_branch) return branches(c);
  if(c->kind==K_memory) {
    volatile uint32_t *p=c->mode==2?shared_data:data[h]; unsigned words=c->bytes/4; uint64_t sum=0;
    if(c->mode==1) { unsigned at=0; for(unsigned i=0;i<c->n;++i) at=p[at]; return at; }
    if(c->mode==4&&h==2) {
      for(unsigned pass=0;pass<c->n;++pass) for(unsigned i=0;i<words;i+=8) { VSTORE(32,v8,p+i); }
      return (uint64_t)c->n*words;
    }
    for(unsigned pass=0;pass<c->n;++pass) for(unsigned i=0;i<words;++i) {
      if(c->mode==3&&h==2) { p[i]=1; ++sum; } else sum+=p[i];
    } return sum;
  }
  if(c->kind==K_atomic) {
    uint64_t *p=c->mode==0?&shared_counter:c->mode==1?&false_shared[h]:&separated[h].value;
    for(unsigned i=0;i<c->n;++i) { __atomic_fetch_add(p,1,__ATOMIC_SEQ_CST); }
    return c->n;
  }
  if(c->kind==K_scalar_fp) { for(unsigned i=0;i<c->n;++i) scalar_add(c->sew); return scalar_bits(c->sew); }
  if(c->kind==K_vector_int||c->kind==K_vector_fp) {
    for(unsigned i=0;i<c->n;++i) {
      if(c->kind==K_vector_fp) __asm__ volatile("vfadd.vv v8,v8,v16":::"memory");
      else {
        __asm__ volatile("vadd.vv v8,v8,v16":::"memory");
        if(c->mode) __asm__ volatile("vadd.vv v24,v24,v28":::"memory");
      }
    } vector_drain(h,c); return 0;
  }
  if(c->kind>=K_vme_int&&c->kind<=K_vme_memory) {
    uint64_t sum=0;
    if(c->kind==K_vme_memory&&c->mode==0) for(unsigned i=0;i<c->n;++i) matrix_mac(c);
    for(unsigned i=0;i<c->n;++i) {
      if(c->kind==K_tile_zero) VME_VTZERO(0);
      else if(c->kind==K_row_read) VME_VTMV_V_T(24,vme_tss(0,VME_TSS_ROW,i&31));
      else if(c->kind==K_row_write) VME_VTMV_T_V(vme_tss(0,VME_TSS_ROW,i&31),24);
      else if(c->kind!=K_vme_memory||c->mode) matrix_mac(c);
      if(c->kind==K_vme_memory) {
        volatile uint32_t *p=data[h]; unsigned at=(i*4)%1024;
        sum+=p[at]+p[at+1]+p[at+2]+p[at+3];
      }
    }
    scalar_saved[h]=sum; matrix_drain(h,c); return 0;
  }
  if(c->kind==K_shared_fpu) {
    if(c->mode==0||c->mode==2) for(unsigned i=0;i<c->n;++i) scalar_add(32);
    if(c->mode==1||c->mode==2) for(unsigned i=0;i<c->n;++i) __asm__ volatile("vfadd.vv v8,v8,v16":::"memory");
    if(c->mode==3) for(unsigned i=0;i<c->n;++i) { scalar_add(32); __asm__ volatile("vfadd.vv v8,v8,v16":::"memory"); }
    if(c->mode!=1) scalar_saved[h]=scalar_bits(32);
    if(c->mode) { VSTORE(32,v8,output[h]); }
    return 0;
  }
  if(c->kind==K_pipeline||c->kind==K_pipeline_vme) {
    unsigned producer=c->kind==K_pipeline?c->mode:2;
    unsigned compute=c->kind==K_pipeline?(c->mode+1)%3:c->mode;
    unsigned phase=h==producer?0:h==compute?1:2; uint64_t sum=0;
    for(unsigned iteration=0;iteration<c->n;++iteration) {
      while(__atomic_load_n(&pipeline_stage,__ATOMIC_ACQUIRE)!=3*iteration+phase) {}
      if(phase==0) {
        if(c->kind==K_pipeline) for(unsigned i=0;i<8;++i) { pipeline_input[i]=i+1; sum+=i+1; }
        else for(unsigned i=0;i<32;++i) { pipeline_a[i]=1;pipeline_b[i]=1;sum+=2; }
      } else if(phase==1) {
        if(c->kind==K_pipeline) {
          __asm__ volatile("vle32.v v8,(%0)\n\tvadd.vv v8,v8,v16"::"r"(pipeline_input):"memory");
          VSTORE(32,v8,pipeline_output);memory_fence();
          for(unsigned i=0;i<8;++i) sum+=pipeline_output[i];
        } else {
          vme_vsettnt_e8w4(32);vme_vsettm(32);vme_vsettk(1);VME_VTZERO(0);
          __asm__ volatile("vle8.v v8,(%0)\n\tvle8.v v16,(%1)"::"r"(pipeline_a),"r"(pipeline_b):"memory");
          VME_MM_U_U(0,8,16);matrix_drain(h,c);memory_fence();
          for(unsigned i=0;i<32;++i) { pipeline_output[i]=((uint32_t *)output[h])[i]; sum+=pipeline_output[i]; }
        }
      } else for(unsigned i=0;i<(c->kind==K_pipeline?8U:32U);++i) sum+=pipeline_output[i];
      __atomic_store_n(&pipeline_stage,3*iteration+phase+1,__ATOMIC_RELEASE);
    }
    return sum;
  }
  if(c->kind==K_vme_refusal) {
    uint64_t before=illegal_seen[h];expect_illegal[h]=1;VME_VTDISCARD();memory_fence();
    if(expect_illegal[h]) { expect_illegal[h]=0;return 0; }
    return illegal_seen[h]-before;
  }
  return 0;
}
static uint64_t checksum(unsigned h,const case_t *c,uint64_t value) {
  if(c->kind==K_vector_int||c->kind==K_vector_fp) {
    uint64_t sum=sum_bits(h,vl_saved[h],c->sew,0);
    if(c->kind==K_vector_int&&c->mode) sum+=sum_bits(h,vl_saved[h],c->sew,vl_saved[h]*c->sew/8);
    return sum;
  }
  if(c->kind>=K_vme_int&&c->kind<=K_vme_memory) return sum_bits(h,c->edge*c->tiles,32,0)+scalar_saved[h];
  if(c->kind==K_shared_fpu) return (c->mode?sum_bits(h,8,32,0):0)+scalar_saved[h];
  return value;
}
static void run(const case_t *c) {
  unsigned h=hart_id();
  if(h==0) { done=0; complete=0; shared_counter=0;pipeline_stage=0; for(unsigned i=0;i<3;++i) { false_shared[i]=0; separated[i].value=0; } }
  barrier(); if(c->mask&(1U<<h)) prepare(h,c); barrier();
  if(c->mask&(1U<<h)) {
    memory_fence(); uint64_t start=cycles(),before=retired(),value=kernel(h,c);
    memory_fence(); uint64_t after=retired(),end=cycles();
    results[h]=(result_t){start,end,after-before,checksum(h,c,value)};
    if(__atomic_add_fetch(&complete,1,__ATOMIC_ACQ_REL)==active_count(c->mask)) {
      __atomic_store_n(&done,1,__ATOMIC_RELEASE);
      for(unsigned i=0;i<3;++i) if(!(c->mask&(1U<<i))) send_ipi(i);
    }
  } else for(;;) {
    __asm__ volatile("csrc mstatus,%0"::"r"(8UL):"memory"); unsigned ready=__atomic_load_n(&done,__ATOMIC_ACQUIRE);
    if(!ready) __asm__ volatile("wfi":::"memory");
    __asm__ volatile("csrs mstatus,%0"::"r"(8UL):"memory"); if(ready) break;
  }
  barrier();
  if(h==0) {
    if(c->kind==K_atomic) {
      if(c->mode==0) { if(shared_counter!=(uint64_t)c->n*active_count(c->mask)) ++failed; }
      else for(unsigned i=0;i<3;++i) if(c->mask&(1U<<i)) { if((c->mode==1?false_shared[i]:separated[i].value)!=c->n) ++failed; }
    }
    for(unsigned i=0;i<3;++i) if(c->mask&(1U<<i)) {
      result_t r=results[i]; unsigned pass=r.checksum==c->expected[i]; if(!pass) ++failed;
      putstr("IRIS_REGION {\"case_id\":\""); putstr(c->id); putstr("\",\"region\":\"kernel\",\"hart\":"); putuint(i);
      putstr(",\"start_cycle\":"); putuint(r.start); putstr(",\"end_cycle\":"); putuint(r.end);
      putstr(",\"instret_delta\":"); putuint(r.instret); putstr(",\"checksum\":"); putuint(r.checksum);
      putstr(",\"expected_checksum\":"); putuint(c->expected[i]); putstr(",\"pass\":"); putstr(pass?"true":"false"); putstr("}\n");
    }
  }
  barrier();
}
void benchmark_main(unsigned h) {
  for(unsigned i=0;i<524288;++i) eviction[h][i]=1;
  if(h==0) for(unsigned i=0;i<262144;++i) shared_data[i]=1;
  barrier();
  for(unsigned i=0;i<sizeof(experiments)/sizeof(experiments[0]);++i) run(&experiments[i]);
  if(h==0) { putstr("IRIS_BATCH_DONE {\"failed\":"); putuint(failed); putstr("}\n"); finish(failed?1:0); }
  for(;;) __asm__ volatile("wfi");
}
