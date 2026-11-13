/* Matched signed-I8 GEMM schedule ablation. Not full quantized inference. */
#include <zephyr/kernel.h>
#include <zephyr/devicetree.h>
#include <zephyr/sys/sys_io.h>
#include <zephyr/arch/riscv/iris_vme.h>
#include <stdint.h>
#include <string.h>
#include "vme_panel_b_i8.h"
#include "vme_pack_at_i8.h"
enum { MAX_A=128*16384, MAX_B=8192*8192, MAX_C=32*9216, PASSES=3 };
typedef struct {unsigned m,n,k;} shape;
static const shape shapes[]={{32,64,64},{1,2048,16384},{32,2048,16384},
    {128,2048,16384},{32,8192,8192},{32,9216,2304}};
#define POINTS (sizeof(shapes)/sizeof(shapes[0]))
static unsigned char a_mem[MAX_A+128] __attribute__((aligned(64)));
static unsigned char at_mem[MAX_A+128] __attribute__((aligned(64)));
static unsigned char b_mem[MAX_B+128] __attribute__((aligned(64)));
static unsigned char bp_mem[MAX_B+128] __attribute__((aligned(64)));
static unsigned char c_mem[MAX_C*4+128] __attribute__((aligned(64)));
static unsigned char output_mem[MAX_C*4+128] __attribute__((aligned(64)));
static int8_t b_patterns[3][9216];
static int8_t *a=(int8_t*)a_mem+64,*at=(int8_t*)at_mem+64,*b=(int8_t*)b_mem+64,*bp=(int8_t*)bp_mem+64;
static int32_t *cp=(int32_t*)(c_mem+64),*output=(int32_t*)(output_mem+64);
extern int correction_r2m2_panel64_kn(int32_t*,const int8_t*,const int8_t*,size_t,size_t,size_t,size_t,size_t);
extern void vme_gemm_1x2_reuse(int32_t*,const int8_t*,const int8_t*,const int32_t*,size_t,size_t,size_t);
extern volatile uint64_t tohost;
static struct k_sem start[2],armed,computed,done;
static unsigned phase __attribute__((aligned(64)));
static struct k_thread worker_threads[2],control_thread;
K_THREAD_STACK_DEFINE(rvv_stack,8192);
K_THREAD_STACK_DEFINE(vme_stack,8192);
K_THREAD_STACK_DEFINE(control_stack,8192);
typedef struct {uint64_t cycle,retired,tick;} clock_t;
typedef struct {clock_t begin,inner_begin,inner_end,end;uint64_t prep_ticks,finish_ticks,registration_cycles;int rc;} record;
static record result;
static unsigned point_id,route,pass_id,failed;
static uint64_t factor;
static inline unsigned hart(void){unsigned long x;__asm__ volatile("csrr %0,mhartid":"=r"(x));return x;}
static inline void fence(void){__asm__ volatile("fence rw,rw":::"memory");}
static uint64_t tick(void){return *(volatile uint64_t*)0x0200bff8UL;}
static clock_t sample(void){clock_t s;__asm__ volatile("csrr %0,mcycle":"=r"(s.cycle)::"memory");__asm__ volatile("csrr %0,minstret":"=r"(s.retired)::"memory");s.tick=tick();return s;}
static int av(size_t i){return (int)(i%7)-3;}
static int bv(size_t j){return (int)(j%11)-5;}
static int32_t expected(size_t i,size_t j){return (int32_t)((int64_t)av(i)*bv(j)*(int64_t)factor);}
static void guard(unsigned char*p,size_t bytes){memset(p,0x5a,64);memset(p+64+bytes,0x5a,64);}
static int guards(const unsigned char*p,size_t bytes){for(unsigned i=0;i<64;++i)if(p[i]!=0x5a||p[64+bytes+i]!=0x5a)return -1;return 0;}
static void initialize(const shape*s){
 factor=0;
 for(size_t j=0;j<s->n;++j)for(unsigned phase=0;phase<3;++phase)b_patterns[phase][j]=(int8_t)(bv(j)*(int)(phase+1));
 for(size_t kk=0;kk<s->k;++kk){factor+=(kk%4+1)*(kk%3+1);memcpy(b+kk*s->n,b_patterns[kk%3],s->n);}
 for(size_t i=0;i<s->m;++i)for(size_t kk=0;kk<s->k;++kk)a[i*s->k+kk]=(int8_t)(av(i)*(int)(kk%4+1));
 guard(a_mem,s->m*s->k);guard(at_mem,s->m*s->k);guard(b_mem,s->n*s->k);guard(bp_mem,s->n*s->k);
 guard(c_mem,s->m*s->n*4);guard(output_mem,s->m*s->n*4);
}
static void worker(void*x,void*y,void*z){
 unsigned owner=(uintptr_t)x,registered=0;(void)y;(void)z;if(hart()!=0)k_panic();
 for(;;){k_sem_take(&start[owner],K_FOREVER);const shape*s=&shapes[point_id];
  result.rc=0;result.registration_cycles=0;
  if(owner&&!registered){clock_t rb=sample();result.rc=iris_vme_enable();clock_t re=sample();result.registration_cycles=re.cycle-rb.cycle;if(!result.rc)registered=1;}
  fence();result.begin=sample();
  k_sem_give(&armed);while(__atomic_load_n(&phase,__ATOMIC_ACQUIRE)<1)__asm__ volatile("nop":::"memory");fence();result.inner_begin=sample();
  if(!result.rc){
   if(route==0)result.rc=correction_r2m2_panel64_kn(cp,a,bp,s->m,s->n,s->k,0,s->n);
   else if(route==1||route==3){vme_gemm_1x2_reuse(cp,at,b,0,s->m,s->n,s->k);result.rc=0;}
   else result.rc=iris_vme_panel_b_gemm_i8(cp,s->m*s->n*4,at,s->m*s->k,bp,s->n*s->k,s->m,s->n,s->k,64);
  }
  fence();result.inner_end=sample();k_sem_give(&computed);while(__atomic_load_n(&phase,__ATOMIC_ACQUIRE)<2)__asm__ volatile("nop":::"memory");
  fence();result.end=sample();k_sem_give(&done);
 }
}
static int validate(const shape*s,uint64_t*sum){
 if(result.rc)return result.rc;
 if(guards(a_mem,s->m*s->k)||guards(at_mem,s->m*s->k)||guards(b_mem,s->n*s->k)||guards(bp_mem,s->n*s->k)||guards(c_mem,s->m*s->n*4)||guards(output_mem,s->m*s->n*4))return -10;
 *sum=0;
 for(size_t i=0;i<s->m;++i)for(size_t j=0;j<s->n;++j){size_t q=i*s->n+j;int32_t want=expected(i,j);if(cp[q]!=want||output[q]!=want)return -11;*sum+=(uint64_t)(uint32_t)output[q]*(q+1);}
 return 0;
}
static void controller(void*x,void*y,void*z){
 (void)x;(void)y;(void)z;if(hart()!=2)k_panic();unsigned completed=0;
 printk("IRIS_PROGRESS v1 START %u\n",(unsigned)(POINTS*5*PASSES));
 for(point_id=0;point_id<POINTS&&!failed;++point_id){const shape*s=&shapes[point_id];uint64_t setup_begin=tick();initialize(s);
  /* AOT-equivalent weight packing is measured separately from repetitions.
   * Both optimized RVV and new VME consume the exact same packed bytes. */
  uint64_t pack_begin=tick();int status=iris_vme_pack_panel_b_i8(bp,s->n*s->k,b,s->n*s->k,s->n,s->k,64);uint64_t setup_end=tick();
  if(status){failed=1;break;}
  printk("IRIS_PANEL_SETUP %u %llu %llu %llu\n",point_id,setup_begin,pack_begin,setup_end);
  for(route=0;route<5&&!failed;++route)for(pass_id=0;pass_id<PASSES&&!failed;++pass_id){
   for(size_t i=0;i<s->m;++i)for(size_t j=0;j<s->n;++j)cp[i*s->n+j]=output[i*s->n+j]=(int32_t)~(uint32_t)expected(i,j);
   __atomic_store_n(&phase,0,__ATOMIC_RELEASE);fence();uint64_t dispatch_begin=tick();k_sem_give(&start[route!=0]);k_sem_take(&armed,K_FOREVER);uint64_t tb=tick();
   if(route>=3){if(iris_vme_pack_at_i8_blocked(at,s->m*s->k,a,s->m*s->k,s->m,s->k,16,64))k_panic();}
   else if(route)for(size_t kk=0;kk<s->k;++kk)for(size_t i=0;i<s->m;++i)at[kk*s->m+i]=a[i*s->k+kk];
   fence();result.prep_ticks=tick()-tb;__atomic_store_n(&phase,1,__ATOMIC_RELEASE);k_sem_take(&computed,K_FOREVER);tb=tick();
   memcpy(output,cp,s->m*s->n*4);fence();result.finish_ticks=tick()-tb;__atomic_store_n(&phase,2,__ATOMIC_RELEASE);k_sem_take(&done,K_FOREVER);uint64_t dispatch_end=tick();
   uint64_t checksum=0;status=validate(s,&checksum);failed=status!=0;
   printk("IRIS_REGION {\"case_id\":\"panel_p%u_c%u_r%u\",\"region\":\"packed_gemm_operator\",\"hart\":0,\"start_cycle\":%llu,\"end_cycle\":%llu,\"start_instret\":%llu,\"end_instret\":%llu,\"instret_delta\":%llu,\"checksum\":%llu,\"warmup\":false,\"pass\":%s}\n",point_id,route,pass_id,result.begin.cycle,result.end.cycle,result.begin.retired,result.end.retired,result.end.retired-result.begin.retired,checksum,status?"false":"true");
   printk("IRIS_PANEL_AB %u %u %u %d %llu %llu %llu %llu %llu %llu %llu %llu %llu %llu\n",point_id,route,pass_id,status,result.begin.tick,result.end.tick,result.inner_begin.cycle,result.inner_end.cycle,result.inner_begin.retired,result.inner_end.retired,result.inner_begin.tick,result.inner_end.tick,result.prep_ticks,result.finish_ticks);
   printk("IRIS_PANEL_DISPATCH %u %u %u %llu %llu %llu\n",point_id,route,pass_id,dispatch_begin,dispatch_end,result.registration_cycles);
   if(!failed)printk("IRIS_PROGRESS v1 DONE %u panel_p%u_c%u_r%u %llu\n",++completed,point_id,route,pass_id,checksum);
  }
 }
 printk("IRIS_BATCH_DONE passed=%u failed=%u\n",completed,failed);if(!failed)printk("DONE\n");
#if DT_NODE_HAS_COMPAT(DT_CHOSEN(zephyr_console),sifive_uart0)
 uintptr_t uart=DT_REG_ADDR(DT_CHOSEN(zephyr_console));uint32_t ctrl=sys_read32(uart+8);sys_write32((ctrl&~(0x1ffu<<16))|(1u<<16),uart+8);while(!(sys_read32(uart+0x14)&1))k_yield();k_sleep(K_MSEC(1));
#endif
 fence();tohost=failed?3:1;fence();for(;;)__asm__ volatile("wfi");
}
int main(void){
 struct k_sem*sems[]={&start[0],&start[1],&armed,&computed,&done};for(unsigned i=0;i<5;++i)k_sem_init(sems[i],0,1);
 k_tid_t w0=k_thread_create(&worker_threads[0],rvv_stack,K_THREAD_STACK_SIZEOF(rvv_stack),worker,(void*)0,NULL,NULL,K_PRIO_COOP(0),0,K_FOREVER);
 k_tid_t w1=k_thread_create(&worker_threads[1],vme_stack,K_THREAD_STACK_SIZEOF(vme_stack),worker,(void*)1,NULL,NULL,K_PRIO_COOP(0),0,K_FOREVER);
 k_tid_t c=k_thread_create(&control_thread,control_stack,K_THREAD_STACK_SIZEOF(control_stack),controller,NULL,NULL,NULL,K_PRIO_COOP(0),0,K_FOREVER);
 if(k_thread_cpu_pin(w0,0)||k_thread_cpu_pin(w1,0)||k_thread_cpu_pin(c,2))k_panic();
 k_thread_start(w0);k_thread_start(w1);k_thread_start(c);
 for(;;)k_sleep(K_SECONDS(3600));
}
