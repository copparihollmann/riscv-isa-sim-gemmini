#include "runtime.h"
#include "vme.h"
typedef struct{const char*id;unsigned m,n,k,fp8,hart,trial;uint64_t golden;}case_t;
#include "cases.inc"
static uint8_t avec[2][32] __attribute__((aligned(64))),bvec[2][32] __attribute__((aligned(64)));
static uint32_t rowbuf[2][32] __attribute__((aligned(64)));
static uint32_t output[2][256*256] __attribute__((aligned(64)));
static volatile unsigned completed;
static unsigned failed;
typedef struct{uint64_t start,end,instret,mtime_before,mtime_after,checksum,failed,words;}record_t;
volatile record_t matrix_records[CASE_COUNT];
volatile uint64_t matrix_measurements_done=UINT64_MAX;
static int aval(unsigned i,unsigned h){int v=1+(i+h)%3;return i&1?-v:v;}
static int bval(unsigned j,unsigned h){int v=1+(j+2*h)%4;return j&1?-v:v;}
static uint8_t e4(int v){unsigned sign=v<0?128:0;unsigned a=v<0?-v:v;return sign+(a==1?0x38:a==2?0x40:a==3?0x44:0x48);}
static uint32_t f32(int v){unsigned sign=v<0?0x80000000U:0;unsigned a=v<0?-v:v;if(!a)return 0;unsigned e=31-__builtin_clz(a);return sign|((e+127)<<23)|((a<<(23-e))&0x7fffff);}
static uint32_t expected(const case_t*c,unsigned i,unsigned j){int v=aval(i,c->hart)*bval(j,c->hart)*(int)c->k;return c->fp8?f32(v):(uint32_t)v;}
static uint64_t hash(const uint32_t*p,unsigned n){uint64_t h=14695981039346656037ULL;for(unsigned i=0;i<n;++i)for(unsigned b=0;b<4;++b)h=(h^((p[i]>>(8*b))&255))*1099511628211ULL;return h;}
static void initialize(void){vme_vsettnt_e8w4(32);vme_vsettm(32);vme_vsettk(1);VME_VTZERO(0);VME_VTZERO(1);VME_VTZERO(2);VME_VTZERO(3);memory_fence();}
static __attribute__((noinline))void kernel(const case_t*c){
 const unsigned h=c->hart;
 for(unsigned mi=0;mi<c->m;mi+=32)for(unsigned nj=0;nj<c->n;nj+=32){
  unsigned tm=c->m-mi<32?c->m-mi:32,tn=c->n-nj<32?c->n-nj:32;
  for(unsigned i=0;i<tm;++i){int v=aval(mi+i,h);avec[h][i]=c->fp8?e4(v):(uint8_t)v;}
  for(unsigned j=0;j<tn;++j){int v=bval(nj+j,h);bvec[h][j]=c->fp8?e4(v):(uint8_t)v;}
  if(c->fp8)vme_vsettnt_e8w4(tn);else vme_vsettnt_e8w4_alt(tn);
  vme_vsettm(tm);vme_vsettk(1);VME_VTZERO(0);
  __asm__ volatile("vle8.v v8,(%0)\nvle8.v v16,(%1)"::"r"(avec[h]),"r"(bvec[h]):"memory");
  for(unsigned k=0;k<c->k;++k){if(c->fp8){VME_MM_E4_E4(0,8,16);}else{VME_MM_S_S(0,8,16);}}
  vme_vsettnt_e32w1(tn);
  for(unsigned i=0;i<tm;++i){VME_VTMV_V_T(24,vme_tss(0,VME_TSS_ROW,i));__asm__ volatile("vse32.v v24,(%0)"::"r"(rowbuf[h]):"memory");memory_fence();for(unsigned j=0;j<tn;++j)output[h][(mi+i)*c->n+nj+j]=rowbuf[h][j];}
 }
 memory_fence();
}
static void emit(unsigned id){const case_t*c=&cases[id];record_t r=matrix_records[id];
 putstr("IRIS_REGION {\"case_id\":\"");putstr(c->id);putstr("\",\"suite\":\"pow2_matrix\",\"region\":\"kernel\",\"hart\":");putuint(c->hart);putstr(",\"trial_id\":");putuint(c->trial);putstr(",\"m\":");putuint(c->m);putstr(",\"n\":");putuint(c->n);putstr(",\"k\":");putuint(c->k);putstr(",\"dtype\":\"");putstr(c->fp8?"fp8-e4m3-e4m3-f32":"int8-signed-i32");
 putstr("\",\"start_cycle\":");putuint(r.start);putstr(",\"end_cycle\":");putuint(r.end);putstr(",\"instret_delta\":");putuint(r.instret);putstr(",\"mtime_before\":");putuint(r.mtime_before);putstr(",\"mtime_after\":");putuint(r.mtime_after);putstr(",\"mtime_hz\":500000,\"source_core_cycles_per_mtime_tick\":1000,\"mtime_scope\":\"encloses_CSR_ROI_with_sampling_overhead\",\"mtime_quantization_error_bound_core_cycles\":1000");
 putstr(",\"words\":");putuint(r.words);putstr(",\"failed_words\":");putuint(r.failed);putstr(",\"checksum\":");putuint(r.checksum);putstr(",\"expected_checksum\":");putuint(c->golden);putstr(",\"pass\":");putstr(!r.failed&&r.checksum==c->golden?"true":"false");putstr("}\n");
}
void benchmark_main(unsigned h){
 __asm__ volatile("csrw fcsr,zero":::"memory");if(h==2){expect_illegal[2]=1;VME_VTDISCARD();if(expect_illegal[2]||illegal_seen[2]!=1)fail(h,252,0,0);}else initialize();barrier();if(h==0){putstr("IRIS_HART2_VME_REFUSAL {\"hart\":2,\"illegal_seen\":");putuint(illegal_seen[2]);putstr("}\n");}barrier();
 for(unsigned id=0;id<CASE_COUNT;++id){const case_t*c=&cases[id];
  if(h==0)completed=0;barrier();
  if(h==c->hart){
   for(unsigned i=0;i<c->m;++i)for(unsigned j=0;j<c->n;++j)((volatile uint32_t*)output[h])[i*c->n+j]=expected(c,i,j)^UINT32_MAX;
   memory_fence();uint64_t tb=mtime(),ir=retired(),start=cycles();
#ifndef IRIS_MATRIX_SKIP_KERNEL
   kernel(c);
#endif
   uint64_t end=cycles(),ir1=retired(),ta=mtime(),errors=0;
   for(unsigned i=0;i<c->m;++i)for(unsigned j=0;j<c->n;++j)errors+=output[h][i*c->n+j]!=expected(c,i,j);
   uint64_t checksum=hash(output[h],c->m*c->n);matrix_records[id]=(record_t){start,end,ir1-ir,tb,ta,checksum,errors,c->m*c->n};if(errors||checksum!=c->golden)++failed;
   __atomic_store_n(&completed,1,__ATOMIC_RELEASE);for(unsigned p=0;p<3;++p)if(p!=h)send_ipi(p);
  }else for(;;){__asm__ volatile("csrc mstatus,%0"::"r"(8UL):"memory");unsigned v=__atomic_load_n(&completed,__ATOMIC_ACQUIRE);if(!v)__asm__ volatile("wfi":::"memory");__asm__ volatile("csrs mstatus,%0"::"r"(8UL):"memory");if(v)break;}
  barrier();if(h==0)emit(id);barrier();
 }
 if(h==0){memory_fence();matrix_measurements_done=0;memory_fence();putstr("IRIS_BATCH_DONE {\"failed\":");putuint(failed);putstr(",\"cases\":");putuint(CASE_COUNT);putstr(",\"regions\":");putuint(CASE_COUNT);putstr(",\"trials\":3}\n");finish(failed?1:0);}for(;;)__asm__ volatile("wfi");
}
