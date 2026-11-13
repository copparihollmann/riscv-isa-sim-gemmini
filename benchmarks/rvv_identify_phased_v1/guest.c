#include "runtime.h"
#include "vme.h"
#include "uart_drain.h"
typedef struct {const char*id;unsigned kind,sew,lmul,mode,n,bytes,hart,trial,vl,streams;} case_t;
#include "cases.inc"
#define CASES 1908
typedef struct __attribute__((aligned(64))) {uint64_t ci,hart,start,issued,end,ir0,ir1,ir2,checksum,expected,mismatch,checked,vl,time0,time1,msip0,msip1;} record_t;
volatile record_t rvv_records[CASES];
volatile uint64_t rvv_record_count,rvv_measurements_done=UINT64_MAX;
typedef struct __attribute__((aligned(128))){unsigned value;} token_t;
static token_t parked[3],phase_failures[3];
static token_t completion __attribute__((section(".data")))={0};
static unsigned char output[3][1024] __attribute__((aligned(128)));
static uint32_t input[3][256] __attribute__((aligned(128))),target[3][256] __attribute__((aligned(128)));
static void io_fence(void){__asm__ volatile("fence iorw,iorw":::"memory");}
static unsigned msip(void){unsigned long x;__asm__ volatile("csrr %0,mip":"=r"(x));return(x>>3)&1;}
static void clear_ipi(unsigned h){*(volatile uint32_t*)(IRIS_CLINT+4*h)=0;io_fence();}
/* File-backed phase0. Peers clear before announcing startup readiness.
 * MIE remains masked across phase-test/WFI; pending MSIP wakes without a trap.
 * Only phase0->1 and1->2 send IPIs. Earlier harts never resume work. */
static void wait_phase(unsigned h){
 __atomic_store_n(&parked[h].value,1,__ATOMIC_RELEASE);io_fence();
 if(h==0){for(unsigned p=1;p<3;++p)while(!__atomic_load_n(&parked[p].value,__ATOMIC_ACQUIRE)){}io_fence();return;}
 while(__atomic_load_n(&completion.value,__ATOMIC_ACQUIRE)<h)__asm__ volatile("wfi":::"memory");
 while(!msip()){__asm__ volatile("wfi":::"memory");}
 clear_ipi(h);
}
#define SETV(S,M) case S*16+M:__asm__ volatile("vsetvli %0,%1,e"#S",m"#M",ta,ma":"=r"(vl):"r"(wanted):"memory");break
static unsigned configure(const case_t*c){unsigned long vl=0,wanted=c->vl;switch(c->sew*16+c->lmul){SETV(8,1);SETV(8,2);SETV(8,4);SETV(8,8);SETV(16,1);SETV(16,2);SETV(16,4);SETV(16,8);SETV(32,1);SETV(32,2);SETV(32,4);SETV(32,8);SETV(64,1);SETV(64,2);SETV(64,4);SETV(64,8);}return vl;}
static uint64_t fpbits(unsigned n,unsigned sew){unsigned e=0;while((1U<<(e+1))<=n)++e;unsigned mant=sew==16?10:sew==32?23:52,bias=sew==16?15:sew==32?127:1023;return((uint64_t)(bias+e)<<mant)|((uint64_t)(n-(1U<<e))<<(mant-e));}
static uint64_t expected_word(const case_t*c,unsigned stream,unsigned i){unsigned v=0;if(c->kind<2)v=c->n+(c->mode==2&&stream);else if(c->kind==2)v=i+3;else if(c->kind==3)v=3;else if(c->kind==4)v=i+3+stream;else if(c->kind==5)v=stream?c->n:i+3;else if(c->kind==6)v=stream?c->n:3;else v=6;return c->kind==1?fpbits(v,c->sew):v;}
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
static void __attribute__((unused)) kernel(unsigned h,const case_t*c){
 for(unsigned i=0;i<c->n;++i){
  if(c->kind==0){__asm__ volatile("vadd.vv v8,v8,v16":::"memory");if(c->mode==1)__asm__ volatile("vadd.vv v24,v24,v16":::"memory");if(c->mode==2)__asm__ volatile("vadd.vv v24,v8,v16":::"memory");}
  else if(c->kind==1){__asm__ volatile("vfadd.vv v8,v8,v16":::"memory");if(c->mode==1)__asm__ volatile("vfadd.vv v24,v24,v16":::"memory");if(c->mode==2)__asm__ volatile("vfadd.vv v24,v8,v16":::"memory");}
  else if(c->kind==2)__asm__ volatile("vle32.v v8,(%0)"::"r"(input[h]):"memory");
  else if(c->kind==3)__asm__ volatile("vse32.v v8,(%0)"::"r"(target[h]):"memory");
  else if(c->kind==4)__asm__ volatile("vle32.v v8,(%0)\nvadd.vv v24,v8,v16"::"r"(input[h]):"memory");
  else if(c->kind==5)__asm__ volatile("vle32.v v8,(%0)\nvadd.vi v24,v24,1"::"r"(input[h]):"memory");
  else if(c->kind==6)__asm__ volatile("vse32.v v8,(%0)\nvadd.vi v24,v24,1"::"r"(target[h]):"memory");
  else if(c->kind==7) VME_VTMV_V_T(24,vme_tss(0,VME_TSS_ROW,i&31));
  else if(c->kind==8) VME_MM_U_U(0,8,16);
  else VME_MM_E4_E4(0,8,16);
 }
}
#define STORE(S,R,P) __asm__ volatile("vse" #S ".v " #R ",(%0)"::"r"(P):"memory")
static void save_vector(unsigned h,const case_t*c){
 void*p=output[h];void*q=output[h]+c->bytes;
 if(c->kind==3||c->kind==6){for(unsigned i=0;i<c->bytes/4;++i)((uint32_t*)p)[i]=target[h][i];if(c->kind==6)STORE(32,v24,q);return;}
 if(c->kind==7){STORE(32,v24,p);return;}
 if(c->sew==8){STORE(8,v8,p);if(c->streams==2)STORE(8,v24,q);}
 if(c->sew==16){STORE(16,v8,p);if(c->streams==2)STORE(16,v24,q);}
 if(c->sew==32){STORE(32,v8,p);if(c->streams==2)STORE(32,v24,q);}
 if(c->sew==64){STORE(64,v8,p);if(c->streams==2)STORE(64,v24,q);}
}
static uint64_t word(unsigned h,unsigned sew,unsigned i){if(sew==8)return output[h][i];if(sew==16)return((uint16_t*)output[h])[i];if(sew==32)return((uint32_t*)output[h])[i];return((uint64_t*)output[h])[i];}
static unsigned emit_section(unsigned h){unsigned failed=0,regions=0;for(unsigned i=0;i<CASES;++i){const case_t*c=&experiments[i];if(c->hart!=h)continue;++regions;record_t r=rvv_records[i];unsigned pass=r.mismatch==0&&r.checksum==r.expected&&r.msip0==0&&r.msip1==0;if(!pass)++failed;
 putstr("IRIS_REGION {\"case_id\":\"");putstr(c->id);putstr("\",\"parent_case_id\":\"");putstr(parent_ids[i]);putstr("\",\"suite\":\"rvv_identify\",\"region\":\"kernel\",\"hart\":");putuint(r.hart);putstr(",\"trial_id\":");putuint(c->trial);
#define FIELD(N,V) putstr(",\""N"\":");putuint(V)
 FIELD("kind",c->kind);FIELD("sew",c->sew);FIELD("lmul",c->lmul);FIELD("mode",c->mode);FIELD("operations",c->n);FIELD("vector_bytes",c->bytes);FIELD("vl",r.vl);FIELD("checked_words",r.checked);FIELD("mismatch_or",r.mismatch);FIELD("start_cycle",r.start);FIELD("issue_cycle",r.issued);FIELD("end_cycle",r.end);FIELD("instret_delta",r.ir2-r.ir0);FIELD("issue_instret_delta",r.ir1-r.ir0);FIELD("drain_instret_delta",r.ir2-r.ir1);FIELD("mtime_before",r.time0);FIELD("mtime_after",r.time1);FIELD("msip_before",r.msip0);FIELD("msip_after",r.msip1);FIELD("checksum",r.checksum);FIELD("expected_checksum",r.expected);
 putstr(",\"pass\":");putstr(pass?"true":"false");putstr("}\n");
#undef FIELD
 }putstr("IRIS_HART_SECTION {\"hart\":");putuint(h);putstr(",\"regions\":");putuint(regions);putstr(",\"failed\":");putuint(failed);putstr("}\n");return failed;}
void benchmark_main(unsigned h){__asm__ volatile("csrc mstatus,%0\ncsrw mie,%0"::"r"(8UL):"memory");set_timer(h,UINT64_MAX);io_fence();clear_ipi(h);wait_phase(h);
 for(unsigned ci=0;ci<CASES;++ci){const case_t*c=&experiments[ci];if(c->hart!=h)continue;setup(h,c);
  uint64_t before=msip(),t0=mtime(),start=cycles(),ir0=retired();
#ifndef IRIS_SKIP_RVV_KERNEL
  kernel(h,c);
#endif
  uint64_t ir1=retired(),issued=cycles();memory_fence();uint64_t ir2=retired(),end=cycles(),t1=mtime(),after=msip();if(c->kind<8)save_vector(h,c);memory_fence();
  uint64_t sum=14695981039346656037ULL,expected=sum,mismatch=0;unsigned count=0;
  if(c->kind>=8){
   vme_vsettnt_e32w1(32);vme_vsettm(32);
   for(unsigned row=0;row<32;++row){VME_VTMV_V_T(24,vme_tss(0,VME_TSS_ROW,row));STORE(32,v24,output[h]);memory_fence();
    for(unsigned col=0;col<32;++col){uint64_t actual=((uint32_t*)output[h])[col],value=c->n*c->mode*(c->kind==8?6:1),wanted=(row<c->vl&&col<c->vl)?(c->kind==8?value:fpbits(value,32)):0;mismatch|=actual^wanted;sum=(sum^actual)*1099511628211ULL;expected=(expected^wanted)*1099511628211ULL;++count;}
   }
  }else{
  for(unsigned stream=0;stream<c->streams;++stream)for(unsigned j=0;j<c->vl;++j){uint64_t actual=word(h,c->sew,count),wanted=expected_word(c,stream,j);mismatch|=actual^wanted;sum=(sum^actual)*1099511628211ULL;expected=(expected^wanted)*1099511628211ULL;++count;}
  }
  rvv_records[ci]=(record_t){ci,h,start,issued,end,ir0,ir1,ir2,sum,expected,mismatch,count,c->vl,t0,t1,before,after};
 }
 memory_fence();unsigned failed=emit_section(h);__atomic_store_n(&phase_failures[h].value,failed,__ATOMIC_RELEASE);iris_uart_drain();io_fence();
 if(h<2){__atomic_store_n(&completion.value,h+1,__ATOMIC_RELEASE);io_fence();send_ipi(h+1);io_fence();for(;;)__asm__ volatile("wfi");}
 rvv_record_count=CASES;memory_fence();rvv_measurements_done=0;memory_fence();
 failed=__atomic_load_n(&phase_failures[0].value,__ATOMIC_ACQUIRE)+__atomic_load_n(&phase_failures[1].value,__ATOMIC_ACQUIRE)+failed;
 putstr("IRIS_BATCH_DONE {\"failed\":");putuint(failed);putstr(",\"cases\":1908,\"regions\":1908,\"trials\":3}\n");finish(failed?1:0);
}
