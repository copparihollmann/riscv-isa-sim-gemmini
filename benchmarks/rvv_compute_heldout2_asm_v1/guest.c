#include "runtime.h"
#include "vme.h"
#include "uart_drain.h"
typedef struct {const char*id;unsigned kind,sew,lmul,mode,n,bytes,hart,trial,vl,streams;} case_t;
#include "cases.inc"
#define CASES 1320
typedef struct __attribute__((aligned(64))) {uint64_t ci,hart,start,issued,end,ir0,ir1,ir2,checksum,expected,mismatch,checked,vl,time0,time1,msip0,msip1;} record_t;
volatile record_t rvv_records[CASES];
volatile uint64_t rvv_record_count,rvv_measurements_done=UINT64_MAX;
typedef struct __attribute__((aligned(128))){unsigned value;} token_t;
static token_t parked[3];
static token_t completion __attribute__((section(".data")))={0};
static unsigned char output[3][1024] __attribute__((aligned(128)));
static uint32_t input[3][256] __attribute__((aligned(128))),target[3][256] __attribute__((aligned(128)));
static void io_fence(void){__asm__ volatile("fence iorw,iorw":::"memory");}
static unsigned msip(void){unsigned long x;__asm__ volatile("csrr %0,mip":"=r"(x));return(x>>3)&1;}
static void clear_ipi(unsigned h){*(volatile uint32_t*)(IRIS_CLINT+4*h)=0;io_fence();}
/* File-backed phase0. Peers clear before announcing startup readiness.
 * MIE remains masked across phase-test/WFI; pending MSIP wakes without a trap.
 * Only phase0->1 sends an IPI. Hart2 and finishedhart0 never resume work. */
static void wait_phase(unsigned h){
 __atomic_store_n(&parked[h].value,1,__ATOMIC_RELEASE);io_fence();
 if(h==2){for(;;)__asm__ volatile("wfi");}
 if(h==0){for(unsigned p=1;p<3;++p)while(!__atomic_load_n(&parked[p].value,__ATOMIC_ACQUIRE)){}io_fence();return;}
 while(__atomic_load_n(&completion.value,__ATOMIC_ACQUIRE)<h)__asm__ volatile("wfi":::"memory");
 while(!msip()){__asm__ volatile("wfi":::"memory");}
 clear_ipi(h);
}
#define SETV(S,M) case S*16+M:__asm__ volatile("vsetvli %0,%1,e"#S",m"#M",ta,ma":"=r"(vl):"r"(wanted):"memory");break
static unsigned configure(const case_t*c){unsigned long vl=0,wanted=c->vl;switch(c->sew*16+c->lmul){SETV(8,1);SETV(8,2);SETV(8,4);SETV(8,8);SETV(16,1);SETV(16,2);SETV(16,4);SETV(16,8);SETV(32,1);SETV(32,2);SETV(32,4);SETV(32,8);SETV(64,1);SETV(64,2);SETV(64,4);SETV(64,8);}return vl;}
static uint64_t fpbits(unsigned n,unsigned sew){unsigned e=0;while((1U<<(e+1))<=n)++e;unsigned mant=sew==16?10:sew==32?23:52,bias=sew==16?15:sew==32?127:1023;return((uint64_t)(bias+e)<<mant)|((uint64_t)(n-(1U<<e))<<(mant-e));}
static uint64_t expected_word(const case_t*c,unsigned stream,unsigned i){unsigned v=0;
 if(c->kind<2)v=c->n+(c->mode==2&&stream);else if(c->kind==2)v=i+3;else if(c->kind==3)v=3;else if(c->kind==4)v=i+3+stream;else if(c->kind==5)v=stream?c->n:i+3;else if(c->kind==6)v=stream?c->n:3;else v=6;if(c->kind==0&&c->sew==8)v &= 255U;return c->kind==1?fpbits(v,c->sew):v;}
static void setup(unsigned h,const case_t*c){
 for(unsigned i=0;i<256;++i){input[h][i]=i+3;target[h][i]=0xa5a5a5a5U;}for(unsigned i=0;i<1024;++i)output[h][i]=0xa5;
 __asm__ volatile("csrw vstart,zero\ncsrw vxrm,zero\ncsrw fcsr,zero":::"memory");
 if(configure(c)!=c->vl)fail(h,1,c->sew,c->lmul);
 uint64_t one=c->kind==1?fpbits(1,c->sew):1,initial=(c->kind==3||c->kind==6)?3:0;
 __asm__ volatile("vmv.v.x v8,%0\nvmv.v.x v16,%1\nvmv.v.i v24,0"::"r"(initial),"r"(one):"memory");
 if(c->kind==7){vme_vsettnt_e8w4(32);vme_vsettm(32);vme_vsettk(1);VME_VTZERO(0);__asm__ volatile("vmv.v.i v8,2\nvmv.v.i v16,3":::"memory");VME_MM_U_U(0,8,16);memory_fence();vme_vsettnt_e32w1(32);__asm__ volatile("vmv.v.i v24,0":::"memory");}
 if(c->kind>=8){
  vme_vsettnt_e8w4(32);vme_vsettm(32);vme_vsettk(c->mode);VME_VTZERO(0);VME_VTZERO(1);VME_VTZERO(2);VME_VTZERO(3);
  vme_vsettnt_e8w4(c->vl);vme_vsettm(c->vl);vme_vsettk(c->mode);
  unsigned char*a=(unsigned char*)input[h],*b=a+128;for(unsigned i=0;i<128;++i){a[i]=c->kind==8?2:0x38;b[i]=c->kind==8?3:0x38;}
  __asm__ volatile("vle8.v v8,(%0)\nvle8.v v10,(%0)\nvle8.v v12,(%0)\nvle8.v v14,(%0)\nvle8.v v16,(%1)\nvle8.v v18,(%1)\nvle8.v v20,(%1)\nvle8.v v22,(%1)"::"r"(a),"r"(b):"memory");
 }
 memory_fence();
}
typedef void (*kernel_fn)(unsigned,const void*,void*);
extern void asm_measure(volatile record_t*,kernel_fn,unsigned,const void*,void*);
extern void asm_integer0(unsigned,const void*,void*),asm_integer1(unsigned,const void*,void*),asm_integer2(unsigned,const void*,void*);
extern void asm_fp0(unsigned,const void*,void*),asm_fp1(unsigned,const void*,void*),asm_fp2(unsigned,const void*,void*);
extern void asm_load(unsigned,const void*,void*),asm_store(unsigned,const void*,void*),asm_load_use(unsigned,const void*,void*),asm_load_independent(unsigned,const void*,void*),asm_store_compute(unsigned,const void*,void*);
extern void asm_row3(unsigned,const void*,void*),asm_row12(unsigned,const void*,void*),asm_row48(unsigned,const void*,void*),asm_row192(unsigned,const void*,void*);
extern void asm_matrix_int(unsigned,const void*,void*),asm_matrix_fp8(unsigned,const void*,void*);
static kernel_fn select_kernel(unsigned h,const case_t*c){
 if(c->kind==0){kernel_fn f[]={asm_integer0,asm_integer1,asm_integer2};return f[c->mode];}
 if(c->kind==1){kernel_fn f[]={asm_fp0,asm_fp1,asm_fp2};return f[c->mode];}
 if(c->kind==2)return asm_load;
 if(c->kind==3)return asm_store;
 if(c->kind==4)return asm_load_use;
 if(c->kind==5)return asm_load_independent;
 if(c->kind==6)return asm_store_compute;
 if(c->kind==7){switch(c->n){case 3:return asm_row3;case 12:return asm_row12;case 48:return asm_row48;case 192:return asm_row192;}}
 if(c->kind==8)return asm_matrix_int;
 if(c->kind==9)return asm_matrix_fp8;
 fail(h,2,c->kind,c->n);
}
#define STORE(S,R,P) __asm__ volatile("vse" #S ".v " #R ",(%0)"::"r"(P):"memory")
static void save_vector(unsigned h,const case_t*c){
 void*p=output[h];void*q=output[h]+c->bytes;
 if(c->kind==3||c->kind==6){for(unsigned i=0;i<c->bytes/4;++i)((uint32_t*)p)[i]=target[h][i];
 if(c->kind==6){STORE(32,v24,q);}
 return;}
 if(c->kind==7){STORE(32,v24,p);return;}
 if(c->sew==8){STORE(8,v8,p);if(c->streams==2)STORE(8,v24,q);}
 if(c->sew==16){STORE(16,v8,p);if(c->streams==2)STORE(16,v24,q);}
 if(c->sew==32){STORE(32,v8,p);if(c->streams==2)STORE(32,v24,q);}
 if(c->sew==64){STORE(64,v8,p);if(c->streams==2)STORE(64,v24,q);}
}
static uint64_t word(unsigned h,unsigned sew,unsigned i){if(sew==8)return output[h][i];if(sew==16)return((uint16_t*)output[h])[i];if(sew==32)return((uint32_t*)output[h])[i];return((uint64_t*)output[h])[i];}
_Static_assert(offsetof(record_t,msip1)==128,"Actual17QwireABI");
static __attribute__((noinline)) void emit(void){
 unsigned failed=0;for(unsigned i=0;i<CASES;++i){const volatile record_t*r=&rvv_records[i];const case_t*c=&experiments[i];unsigned pass=r->mismatch==0&&r->checksum==r->expected&&r->msip0==0&&r->msip1==0;if(!pass)++failed;
 putstr("IRIS_REGION {\"case_id\":\"");putstr(c->id);putstr("\",\"parent_case_id\":\"");putstr(parent_ids[i]);putstr("\",\"suite\":\"rvv_compute_heldout2_asm_v1\",\"region\":\"kernel\",\"hart\":");putuint(r->hart);putstr(",\"trial_id\":");putuint(c->trial);
#define FIELD(N,V) putstr(",\""N"\":");putuint(V)
 FIELD("kind",c->kind);FIELD("sew",c->sew);FIELD("lmul",c->lmul);FIELD("mode",c->mode);FIELD("operations",c->n);FIELD("vector_bytes",c->bytes);FIELD("vl",r->vl);FIELD("checked_words",r->checked);FIELD("mismatch_or",r->mismatch);FIELD("start_cycle",r->start);FIELD("issue_cycle",r->issued);FIELD("end_cycle",r->end);FIELD("instret_delta",r->ir2-r->ir0);FIELD("issue_instret_delta",r->ir1-r->ir0);FIELD("drain_instret_delta",r->ir2-r->ir1);FIELD("mtime_before",r->time0);FIELD("mtime_after",r->time1);FIELD("msip_before",r->msip0);FIELD("msip_after",r->msip1);FIELD("checksum",r->checksum);FIELD("expected_checksum",r->expected);
#undef FIELD
 putstr(",\"pass\":");putstr(pass?"true":"false");putstr("}\n");
 }putstr("IRIS_BATCH_DONE {\"failed\":");putuint(failed);putstr(",\"cases\":1320,\"regions\":1320,\"trials\":3}\n");finish(failed?1:0);
}
void benchmark_main(unsigned h){__asm__ volatile("csrc mstatus,%0\ncsrw mie,%0"::"r"(8UL):"memory");set_timer(h,UINT64_MAX);io_fence();clear_ipi(h);wait_phase(h);
 for(unsigned ci=0;ci<CASES;++ci){const case_t*c=&experiments[ci];if(c->hart!=h)continue;setup(h,c);
  kernel_fn fn=select_kernel(h,c);unsigned blocks=c->kind==7?0:c->n/16;
  fn(blocks,input[h],target[h]); /* explicit body pre-execution outside all CSR ROI */
  setup(h,c); /* full operand/tile/output reset+fence, including omitted-call builds */
  asm_measure(&rvv_records[ci],fn,blocks,input[h],target[h]);
  if(c->kind<8){save_vector(h,c);}
  memory_fence();
  uint64_t sum=14695981039346656037ULL,expected=sum,mismatch=0;unsigned count=0;
  if(c->kind>=8){
   vme_vsettnt_e32w1(32);vme_vsettm(32);
   for(unsigned row=0;row<32;++row){VME_VTMV_V_T(24,vme_tss(0,VME_TSS_ROW,row));STORE(32,v24,output[h]);memory_fence();
    for(unsigned col=0;col<32;++col){uint64_t actual=((uint32_t*)output[h])[col],value=c->n*c->mode*(c->kind==8?6:1),wanted=(row<c->vl&&col<c->vl)?(c->kind==8?value:fpbits(value,32)):0;mismatch|=actual^wanted;sum=(sum^actual)*1099511628211ULL;expected=(expected^wanted)*1099511628211ULL;++count;}
   }
  }else{
  for(unsigned stream=0;stream<c->streams;++stream)for(unsigned j=0;j<c->vl;++j){uint64_t actual=word(h,c->sew,count),wanted=expected_word(c,stream,j);mismatch|=actual^wanted;sum=(sum^actual)*1099511628211ULL;expected=(expected^wanted)*1099511628211ULL;++count;}
  }
  rvv_records[ci].ci=ci;rvv_records[ci].hart=h;
  rvv_records[ci].checksum=sum;rvv_records[ci].expected=expected;rvv_records[ci].mismatch=mismatch;rvv_records[ci].checked=count;rvv_records[ci].vl=c->vl;
 }
 memory_fence();
 if(h==0){__atomic_store_n(&completion.value,1,__ATOMIC_RELEASE);io_fence();send_ipi(1);io_fence();for(;;)__asm__ volatile("wfi");}
 rvv_record_count=CASES;memory_fence();rvv_measurements_done=0;memory_fence();emit();
}
