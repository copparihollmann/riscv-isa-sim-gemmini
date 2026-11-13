/* Independent finite-FADD async checks; never calibration data. */
#include "runtime.h"

typedef struct __attribute__((aligned(64))) {
  uint64_t before, issued, drained, flags, value, fs, vl, failed;
} record_t;
static record_t records[3][3];
static uint64_t outputs[3][4] __attribute__((aligned(64)));

static void run(unsigned h,unsigned kind) {
  const unsigned width=16u<<kind;
  const uint64_t inf=kind==0?0x7c00u:kind==1?0x7f800000u:0x7ff0000000000000ull;
  const uint64_t sign=1ull<<(width-1);
  const uint64_t nan=kind==0?0x7e00u:kind==1?0x7fc00000u:0x7ff8000000000000ull;
  const uint64_t type=0xc0u+((kind+1u)<<3);
  unsigned long vl;
  __asm__ volatile("vsetvl %0,%1,%2\nvmv.v.x v8,%3\nvmv.v.x v16,%4\ncsrw fflags,%5"
      :"=&r"(vl):"r"(4ul),"r"(type),"r"(inf),"r"(inf|sign),"r"(4ul):"memory");
  /* Shuttle can preserve Clean; Rocket source WARL makes nonzero FS Dirty. */
  const unsigned long fs_mask=0x6000ul,fs_clean=0x4000ul;
  __asm__ volatile("csrc mstatus,%0\ncsrs mstatus,%1"::"r"(fs_mask),"r"(fs_clean):"memory");
  const uint64_t before=cycles();
  __asm__ volatile("vfadd.vv v24,v8,v16":::"memory");
  const uint64_t issued=cycles();
  unsigned long flags,fs;
  __asm__ volatile("csrr %0,fflags\ncsrr %1,mstatus":"=r"(flags),"=r"(fs)::"memory");
  const uint64_t drained=cycles();
  if(kind==0)__asm__ volatile("vse16.v v24,(%0)"::"r"(outputs[h]):"memory");
  else if(kind==1)__asm__ volatile("vse32.v v24,(%0)"::"r"(outputs[h]):"memory");
  else __asm__ volatile("vse64.v v24,(%0)"::"r"(outputs[h]):"memory");
  memory_fence();
  unsigned failed=vl!=4||flags!=(h==2?20u:5u)||(fs&fs_mask)!=fs_mask;
  for(unsigned j=0;j<4;++j) {
    uint64_t value=kind==0?((uint16_t*)outputs[h])[j]:kind==1?((uint32_t*)outputs[h])[j]:outputs[h][j];
    failed+=value!=nan;
  }
  records[h][kind]=(record_t){before,issued,drained,flags,nan,fs&fs_mask,vl,failed};
}

void benchmark_main(unsigned h) {
  __asm__ volatile("csrw frm,zero\ncsrw vxrm,zero":::"memory");
  for(unsigned kind=0;kind<3;++kind){barrier();run(h,kind);barrier();}
  if(h==0){unsigned failed=0;for(unsigned i=0;i<3;++i)for(unsigned k=0;k<3;++k){
    record_t*r=&records[i][k];failed+=r->failed;
    putstr("IRIS_FADD_ASYNC ");putuint(i);putstr(" ");putuint(16u<<k);
    putstr(" ");putuint(r->before);putstr(" ");putuint(r->issued);putstr(" ");putuint(r->drained);
    putstr(" ");putuint(r->flags);putstr(" ");putuint(r->value);putstr(" ");putuint(r->fs);
    putstr(" ");putuint(r->failed);putstr("\n");
  }putstr("IRIS_FADD_DONE ");putuint(failed);putstr("\n");finish(failed!=0);}
  for(;;)__asm__ volatile("wfi");
}
