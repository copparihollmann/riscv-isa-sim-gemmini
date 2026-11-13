#include <zephyr/kernel.h>
#include <zephyr/arch/riscv/iris_vme.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/reboot.h>
#include <zephyr/sys/sys_io.h>
#include <zephyr/devicetree.h>
#include <stdint.h>
#include <stddef.h>
#include <errno.h>

#define THREADS 4
#define ROUNDS 8
struct context {
  uint64_t f[32];uint8_t v[1024];
  uint64_t vstart,vl,vtype,vcsr,vlenb,fcsr,mtype;
} __aligned(64);
BUILD_ASSERT(offsetof(struct context,mtype)==1328);
extern void context_load(const struct context *);
extern void context_store(struct context *);
extern void z_iris_vme_tiles_save(void *);
extern void z_iris_vme_tiles_restore(const void *);
static struct context expected[THREADS],observed[THREADS];
static uint32_t tiles[THREADS][4][32][32],readback[THREADS][4][32][32];
static uint8_t inputs_a[THREADS][4][32],inputs_b[THREADS][4][32];
static unsigned generation[THREADS];
static struct k_thread workers[THREADS],producer;
K_THREAD_STACK_ARRAY_DEFINE(stacks,THREADS,8192);
K_THREAD_STACK_DEFINE(producer_stack,8192);
static struct k_sem work[THREADS],enter[THREADS],resume[THREADS];
K_SEM_DEFINE(completed,0,THREADS);
K_SEM_DEFINE(finished,0,THREADS+1);
static struct {uint64_t checksum,ticks;uint32_t saves,restores,visits;unsigned rounds;} results[THREADS];
static uint64_t producer_checksum;
static unsigned hart(void) {unsigned long x;__asm__ volatile("csrr %0,mhartid":"=r"(x));return x;}
static void fail(unsigned id,unsigned round,unsigned field) {
  printk("IRIS_VME_CONTEXT_FATAL {\"thread\":%u,\"hart\":%u,\"round\":%u,\"field\":%u}\n",id,hart(),round,field);k_panic();
}
static uint64_t hash(uint64_t h,const void *p,size_t n) {
  const uint8_t *b=p;for(size_t i=0;i<n;++i) h=(h^b[i])*1099511628211ULL;return h;
}
static void configure(uint64_t code,uint64_t vt,uint64_t tn,uint64_t tm,uint64_t tk,uint64_t start,uint64_t vcsr) {
  __asm__ volatile(".insn r 0x57,7,0x42,x0,%0,%1\n\t"
    ".insn r 0x57,7,0x44,x0,%2,x0\n\t.insn r 0x57,7,0x44,x0,%3,x1\n\t.insn r 0x57,7,0x44,x0,%4,x2\n\t"
    "csrw vstart,%5\n\tcsrw vcsr,%6"::"r"(code),"r"(vt),"r"(tn),"r"(tm),"r"(tk),"r"(start),"r"(vcsr):"memory");
}
static void fill(unsigned id,unsigned round) {
  struct context *s=&expected[id];
  static const unsigned tn[]={17,23,27,31},tm[]={9,11,19,7},tk[]={4,3,1,2};
  for(unsigned i=0;i<32;++i)s->f[i]=0x3ff0000000000000ULL|((uint64_t)(id+1)<<40)|((uint64_t)(round+1)<<24)|((uint64_t)i<<12);
  for(unsigned i=0;i<1024;++i)s->v[i]=(uint8_t)(id*37+round*13+i*7);
  s->vstart=id%3;s->vl=tn[id];s->vtype=id==2?0xd2:0xc0|(id&1?0x100:0);
  s->vcsr=((id%4)<<1)|(id&1);s->vlenb=32;s->fcsr=((id%5)<<5)|((id*3+round)&31);
  s->mtype=(id==2?1:4)|((uint64_t)tk[id]<<5)|((uint64_t)tm[id]<<10);
  for(unsigned t=0;t<4;++t)for(unsigned r=0;r<32;++r)for(unsigned c=0;c<32;++c)
    tiles[id][t][r][c]=0x80000000u^(id*0x1020304u)^(round*0x10001u)^(t*0x100000u)^(r*0x101u)^c;
  /* Bit-copy certification includes signed zeros, infinities, quiet/signaling
   * NaN payloads and all-one integer cells; no FP arithmetic touches these. */
  static const uint32_t special[]={0,0x80000000u,0x7f800000u,0xff800000u,0x7fc01234u,0x7fa05678u,0xffffffffu,1};
  for(unsigned t=0;t<4;++t)for(unsigned c=0;c<8;++c)tiles[id][t][0][c]=special[c];
}
static void compete(unsigned id) {
  unsigned other=id^1;
  if(!(id&1))k_sem_give(&enter[other]);else k_sem_give(&resume[other]);
  int64_t start=k_uptime_get();k_busy_wait(2000);results[id].ticks+=(uint64_t)(k_uptime_get()-start);
  k_sem_take(&resume[id],K_FOREVER);
}
static void release(unsigned id) {
  if(!(id&1))k_sem_give(&resume[id^1]);else k_sem_give(&enter[id^1]);
}
static void operands(unsigned id) {
  const uint8_t *a=&inputs_a[id][0][0],*b=&inputs_b[id][0][0];
  __asm__ volatile(".option push\n\t.option arch,+v\n\t"
    "vle8.v v0,(%0)\n\taddi %0,%0,32\n\tvle8.v v2,(%0)\n\taddi %0,%0,32\n\t"
    "vle8.v v4,(%0)\n\taddi %0,%0,32\n\tvle8.v v6,(%0)\n\t"
    "vle8.v v8,(%1)\n\taddi %1,%1,32\n\tvle8.v v10,(%1)\n\taddi %1,%1,32\n\t"
    "vle8.v v12,(%1)\n\taddi %1,%1,32\n\tvle8.v v14,(%1)\n\t.option pop"
    :"+&r"(a),"+&r"(b)::"memory");
}
static void mac(unsigned id) {
  /* Tile destination differs, and both format bits vary across tasks. */
  switch(id) {
  case 0:__asm__ volatile(".insn r 0x77,0,0x79,x0,x8,x0":::"memory");break;
  case 1:__asm__ volatile(".insn r 0x77,1,0x79,x8,x8,x0":::"memory");break;
  case 2:__asm__ volatile(".insn r 0x77,0,0x79,x17,x8,x0":::"memory");break;
  case 3:__asm__ volatile(".insn r 0x77,1,0x79,x25,x8,x0":::"memory");break;
  }
}
static void zero(unsigned id) {
  switch(id) {
  case 0:__asm__ volatile(".insn r 0x57,6,0x21,x0,x0,x30");break;
  case 1:__asm__ volatile(".insn r 0x57,6,0x21,x8,x0,x30");break;
  case 2:__asm__ volatile(".insn r 0x57,6,0x21,x16,x0,x30");break;
  case 3:__asm__ volatile(".insn r 0x57,6,0x21,x24,x0,x30");break;
  }
}
static void worker(void *arg,void *b,void *c) {
  unsigned id=(uintptr_t)arg;(void)b;(void)c;
  if(iris_vme_enable()!=0||iris_vme_enable()!=-EALREADY)fail(id,0,100);
  uint64_t sum=14695981039346656037ULL;
  /* The ownership ABI explicitly initialized every cell, including padding. */
  z_iris_vme_tiles_save(readback[id]);
  for(unsigned i=0;i<4096;++i)if(((uint32_t *)readback[id])[i])fail(id,0,101);
  for(unsigned round=0;round<ROUNDS;++round) {
    k_sem_take(&work[id],K_FOREVER);
    if(hart()!=((id/2)^(round&1))||generation[id]!=round+1)fail(id,round,102);
    results[id].visits|=1u<<hart();
    k_sem_take(&enter[id],K_FOREVER);fill(id,round);
    z_iris_vme_tiles_restore(tiles[id]);context_load(&expected[id]);
    configure(id==2?1:3,expected[id].vtype,expected[id].vl,expected[id].mtype>>10,(expected[id].mtype>>5)&7,expected[id].vstart,expected[id].vcsr);
    compete(id);
    __asm__ volatile("csrr %0,0xc23":"=r"(observed[id].mtype));context_store(&observed[id]);
    const uint8_t *want=(const uint8_t *)&expected[id],*got=(const uint8_t *)&observed[id];
    for(unsigned i=0;i<1336;++i)if(want[i]!=got[i])fail(id,round,i);
    z_iris_vme_tiles_save(readback[id]);
    for(unsigned t=0;t<4;++t)for(unsigned r=0;r<32;++r)for(unsigned col=0;col<32;++col)
      if(readback[id][t][r][col]!=tiles[id][t][r][col])fail(id,round,200+t);
    sum=hash(sum,&observed[id],1336);sum=hash(sum,readback[id],sizeof(readback[id]));release(id);
    /* Repeat with a matrix MAC as the first vector operation after handoff.
     * This catches OP-VE-only state changes and restores geometry/altfmt. */
    k_sem_take(&enter[id],K_FOREVER);
    configure(1,16,32,32,1,0,0);zero(id);
    for(unsigned r=0;r<32;++r)for(unsigned col=0;col<32;++col)tiles[id][id][r][col]=0;
    configure(3,((id==1||id==2)?0x100:0),4+id,3+id,1+id,0,0);
    operands(id);__asm__ volatile("csrw fcsr,zero");compete(id);mac(id);
    z_iris_vme_tiles_save(readback[id]);
    unsigned value=(id&1)?(id==1?(round&1?0x41000000u:0x40800000u):(round&1?0x41800000u:0x41000000u)):(2u*(round+3)*(id+1));
    for(unsigned r=0;r<3+id;++r)for(unsigned col=0;col<4+id;++col)tiles[id][id][r][col]=value;
    for(unsigned t=0;t<4;++t)for(unsigned r=0;r<32;++r)for(unsigned col=0;col<32;++col)
      if(readback[id][t][r][col]!=tiles[id][t][r][col])fail(id,round,300+t);
    sum=hash(sum,readback[id],sizeof(readback[id]));release(id);
    results[id].rounds=round+1;k_sem_give(&completed);
  }
  results[id].checksum=sum;iris_vme_switch_counts(&results[id].saves,&results[id].restores);k_sem_give(&finished);
}
static void produce(void *a,void *b,void *c) {
  (void)a;(void)b;(void)c;
  if(hart()!=2||iris_vme_enable()!=-ENOTSUP)fail(4,0,400);
  uint64_t sum=14695981039346656037ULL;
  for(unsigned round=0;round<ROUNDS;++round) {
    if(round)for(unsigned id=0;id<THREADS;++id) {
      /* Workers block for the next job. Affinity changes are allowed only
       * after Zephyr confirms they are no longer runnable. */
      int rc;do {rc=k_thread_cpu_pin(&workers[id],(id/2)^(round&1));if(rc==-EINVAL)k_sleep(K_MSEC(1));}while(rc==-EINVAL);
      if(rc||k_thread_cpu_pin(&workers[id],2)!=-ENOTSUP)fail(id,round,401);
    }
    for(unsigned id=0;id<THREADS;++id) {
      unsigned av=id==0?3+round:id==2?253-round:(round&1)?0x40:id==1?0x38:0x3c;
      unsigned bv=id&1?0x40:id==2?254:2;
      for(unsigned k=0;k<4;++k)for(unsigned n=0;n<32;++n){inputs_a[id][k][n]=av;inputs_b[id][k][n]=bv;}
      generation[id]=round+1;k_sem_give(&work[id]);
    }
    for(unsigned id=0;id<THREADS;++id)k_sem_take(&completed,K_FOREVER);
    /* Rocket's ordinary RVV remains useful concurrently with VME workers. */
    uint32_t in[8],out[8];for(unsigned n=0;n<8;++n)in[n]=round*8+n;
    __asm__ volatile(".option push\n\t.option arch,+v\n\tvsetivli zero,8,e32,m1,ta,ma\n\t"
      "vle32.v v0,(%0)\n\tvadd.vi v0,v0,7\n\tvse32.v v0,(%1)\n\t.option pop"::"r"(in),"r"(out):"memory");
    for(unsigned n=0;n<8;++n)if(out[n]!=in[n]+7)fail(4,round,402);
    sum=hash(sum,out,sizeof(out));
  }
  producer_checksum=sum;k_sem_give(&finished);
}
int main(void) {
  for(unsigned id=0;id<THREADS;++id) {
    k_sem_init(&work[id],0,1);k_sem_init(&enter[id],!(id&1),1);k_sem_init(&resume[id],0,1);
    k_tid_t t=k_thread_create(&workers[id],stacks[id],K_THREAD_STACK_SIZEOF(stacks[id]),worker,(void *)(uintptr_t)id,NULL,NULL,5,K_FP_REGS,K_FOREVER);
    if(k_thread_cpu_pin(t,id/2))fail(id,0,403);k_thread_start(t);
  }
  k_tid_t p=k_thread_create(&producer,producer_stack,K_THREAD_STACK_SIZEOF(producer_stack),produce,NULL,NULL,NULL,5,K_FP_REGS,K_FOREVER);
  if(k_thread_cpu_pin(p,2))fail(4,0,404);k_thread_start(p);
  for(unsigned n=0;n<THREADS+1;++n)k_sem_take(&finished,K_FOREVER);
  for(unsigned id=0;id<THREADS;++id) {
    if(results[id].visits!=3||!results[id].saves||!results[id].restores||!results[id].ticks)fail(id,ROUNDS,405);
    printk("IRIS_VME_CONTEXT {\"thread\":%u,\"rounds\":%u,\"hart_mask\":%u,\"checksum\":%llu,\"timer_ticks\":%llu,\"saves\":%u,\"restores\":%u}\n",id,results[id].rounds,results[id].visits,(unsigned long long)results[id].checksum,(unsigned long long)results[id].ticks,results[id].saves,results[id].restores);
  }
  printk("IRIS_VME_PRODUCER {\"hart\":2,\"rounds\":%u,\"checksum\":%llu,\"vme_refused\":true}\n",ROUNDS,(unsigned long long)producer_checksum);
  printk("PASSED explicit VME ownership, competing contexts, compute migration and hart2 producer\n");
  uintptr_t uart=DT_REG_ADDR(DT_CHOSEN(zephyr_console));sys_write32((sys_read32(uart+8)&~(0x1ffu<<16))|(1u<<16),uart+8);
  while(!(sys_read32(uart+0x14)&1))k_yield();k_sleep(K_MSEC(1));__asm__ volatile("fence rw,rw":::"memory");sys_reboot(SYS_REBOOT_COLD);return 0;
}
