#include <zephyr/kernel.h>
#include <zephyr/kernel_structs.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/reboot.h>
#include <zephyr/sys/sys_io.h>
#include <zephyr/devicetree.h>
#include <zephyr/arch/riscv/iris_vme.h>
#include "iris_uart_profile.h"
#include "packet.h"
#include "cases.inc"
const group_t*packet_groups=groups;
const descriptor_t*packet_descriptors=descriptors;
volatile uint8_t output_data[STORAGE_BYTES] __aligned(128);
volatile record_t records[REGIONS] __aligned(128);
volatile uint64_t packet_record_count;
volatile uint64_t packet_measurements_done __attribute__((section(".data")))=UINT64_MAX;
K_THREAD_STACK_ARRAY_DEFINE(stacks,3,4096);
static struct k_thread threads[3];
static struct k_sem start[2],done[2];
K_SEM_DEFINE(controller_ready,0,1);
K_SEM_DEFINE(worker_ready,0,2);
K_SEM_DEFINE(launch,0,1);
K_SEM_DEFINE(never,0,1);
struct __attribute__((aligned(128))) task {volatile uint64_t rid,seq,ack;};
static struct task tasks[2];
unsigned long physical_hart(void){unsigned long x;__asm__ volatile("csrr %0,mhartid":"=r"(x));return x;}
static unsigned logical_cpu(void){struct _cpu*p;__asm__ volatile("csrr %0,mscratch":"=r"(p));return p->id;}
static __attribute__((noreturn)) void fatal(unsigned reason,unsigned gid){printk("IRIS_FATAL {\"reason_code\":%u,\"group\":%u,\"physical_hart\":%lu,\"logical_cpu\":%u}\n",reason,gid,physical_hart(),logical_cpu());k_panic();for(;;){}}
static const unsigned values[16]={1,2,3,4,5,6,7,8,10,12,14,16,20,24,28,32};
static int signed_value(unsigned i){int n=values[i&15];return(i&16)?-n:n;}
/* Integer arithmetic only: all selected finite products are exact FP32 ints. */
static uint32_t integer_fp32(int n){if(!n)return 0;unsigned sign=n<0,u=sign?(unsigned)-n:(unsigned)n,e=0;while((u>>(e+1))!=0)++e;return(sign<<31)|((127+e)<<23)|((u-(1U<<e))<<(23-e));}
static uint8_t integer_fp8(int n,unsigned e5){unsigned sign=n<0,u=sign?(unsigned)-n:(unsigned)n,e=0;while((u>>(e+1))!=0)++e;unsigned m=e5?2:3,bias=e5?15:7;return(sign<<7)|((bias+e)<<m)|(((u-(1U<<e))<<m)>>e);}
static uint32_t expected(const group_t*g,unsigned h,unsigned i){
 if(!g->kind){unsigned a=1+2*((i+g->trial+h)&1),b=3+(i*5+7*g->trial+11*h)%31;uint32_t value=b+g->n*a;return g->sew==32?value:value&((1U<<g->sew)-1);}
 unsigned row=i/g->shape,col=i%g->shape;
 int a,b;if(!g->format){a=1+(row+g->trial+h)%3;b=1+(col+2*g->trial+h)%4;}else{a=signed_value(row+3*g->trial+5*h);b=signed_value(col+7*g->trial+3*h);}
 int product=(int)g->n*a*b;return g->format?integer_fp32(product):(uint32_t)product;
}
static uint64_t load_le(const volatile uint8_t*p,unsigned bytes){uint64_t v=0;for(unsigned b=0;b<bytes;++b)v|=(uint64_t)p[b]<<(8*b);return v;}
static void store_le(volatile uint8_t*p,uint64_t v,unsigned bytes){for(unsigned b=0;b<bytes;++b)p[b]=(uint8_t)(v>>(8*b));}
static void prepare(unsigned rid){
 const descriptor_t*d=&descriptors[rid];const group_t*g=&groups[d->group];unsigned h=d->hart;
 for(unsigned i=0;i<256;++i){inputs_a[h][i]=0;inputs_b[h][i]=0;}
 if(!g->kind){for(unsigned i=0;i<d->elements;++i){store_le(inputs_a[h]+i*d->width,1+2*((i+g->trial+h)&1),d->width);store_le(inputs_b[h]+i*d->width,3+(i*5+7*g->trial+11*h)%31,d->width);}}
 else for(unsigned i=0;i<g->shape;++i){
  if(!g->format){inputs_a[h][i]=1+(i+g->trial+h)%3;inputs_b[h][i]=1+(i+2*g->trial+h)%4;}
  else{inputs_a[h][i]=integer_fp8(signed_value(i+3*g->trial+5*h),g->format>=3);inputs_b[h][i]=integer_fp8(signed_value(i+7*g->trial+3*h),g->format==2||g->format==4);}
 }
 store_le(output_data+d->offset,GUARD,8);store_le(output_data+d->offset+8+d->bytes,GUARD,8);
 for(unsigned i=0;i<d->elements;++i){uint32_t mask=d->width==4?UINT32_MAX:(1U<<(d->width*8))-1;store_le(output_data+d->offset+8+i*d->width,expected(g,h,i)^mask,d->width);}
 records[rid].rid=rid;records[rid].gid=d->group;records[rid].hart=h;records[rid].pin=h;records[rid].elements=d->elements;records[rid].rows=g->kind?g->shape:1;records[rid].cols=g->kind?g->shape:d->elements;
}
static void verify(unsigned rid){const descriptor_t*d=&descriptors[rid];const group_t*g=&groups[d->group];uint64_t sum=14695981039346656037ULL;unsigned failed=0;for(unsigned i=0;i<d->elements;++i){uint64_t value=load_le(output_data+d->offset+8+i*d->width,d->width);if(value!=expected(g,d->hart,i))++failed;sum=(sum^value)*1099511628211ULL;}records[rid].failed=failed;records[rid].checksum=sum;records[rid].guard_ok=load_le(output_data+d->offset,8)==GUARD&&load_le(output_data+d->offset+8+d->bytes,8)==GUARD;}
static void worker(void*a,void*b,void*c){unsigned h=(uintptr_t)a;(void)b;(void)c;
 if(physical_hart()!=h||logical_cpu()!=h)fatal(1,0);
 k_sem_take(&start[h],K_FOREVER);
 printk("IRIS_COMPUTE_READY {\"physical_hart\":%u,\"logical_cpu\":%u,\"pin\":%u,\"before_vme_enable\":true}\n",h,logical_cpu(),h);
 if(iris_vme_enable())fatal(2,0);
 k_sem_give(&worker_ready);
 uint64_t last=0;
 for(;;){k_sem_take(&start[h],K_FOREVER);unsigned rid=tasks[h].rid;uint64_t seq=tasks[h].seq;if(seq!=last+1||rid>=REGIONS||descriptors[rid].hart!=h)fatal(3,rid);records[rid].logical=logical_cpu();if(physical_hart()!=h||records[rid].logical!=h)fatal(4,rid);records[rid].actual_vl=compute_run(rid);last=seq;records[rid].ack=seq;tasks[h].ack=seq;k_sem_give(&done[h]);}
}
static __attribute__((noinline,noreturn)) void emit(void){
 unsigned failed=0;uint64_t elements=0;
 for(unsigned rid=0;rid<REGIONS;++rid){const descriptor_t*d=&descriptors[rid];const group_t*g=&groups[d->group];const volatile record_t*r=&records[rid];if(r->failed||!r->guard_ok)++failed;elements+=d->elements;
 printk("IRIS_REGION {\"case_id\":\"%s\",\"region\":\"kernel\",\"region_index\":%u,\"group\":%u,\"hart\":%llu,\"logical_cpu\":%llu,\"pin\":%llu,\"role\":\"%s\",\"hart_mask\":%u,\"trial\":%u,\"operations\":%u,\"start_cycle\":%llu,\"issue_cycle\":%llu,\"end_cycle\":%llu,\"instret_delta\":%llu,\"checksum\":%llu,\"checked_elements\":%llu,\"failed_elements\":%llu,\"guard_ok\":%s,\"actual_vl\":%llu,\"ack\":%llu}\n",case_ids[d->group],rid,d->group,r->hart,r->logical,r->pin,g->kind?"vme.compute":"rvv.compute",g->mask,g->trial,g->n,r->start,r->issued,r->end,r->ir1-r->ir0,r->checksum,r->elements,r->failed,r->guard_ok?"true":"false",r->actual_vl,r->ack);
 for(unsigned offset=0;offset<d->bytes;offset+=128){char hex[257];unsigned bytes=d->bytes-offset;if(bytes>128)bytes=128;static const char digits[]="0123456789abcdef";for(unsigned j=0;j<bytes;++j){unsigned x=output_data[d->offset+8+offset+j];hex[2*j]=digits[x>>4];hex[2*j+1]=digits[x&15];}hex[2*bytes]=0;printk("IRIS_DATA {\"region_index\":%u,\"hart\":%u,\"offset\":%u,\"little_endian_hex\":\"%s\"}\n",rid,d->hart,offset,hex);}
 }
 printk("IRIS_H2_CONTROL_DONE {\"physical_hart\":%lu,\"logical_cpu\":%u,\"dispatches\":486,\"acknowledgements\":648,\"checked_elements\":%llu,\"scalar_only\":true}\n",physical_hart(),logical_cpu(),elements);
 printk("IRIS_BATCH_DONE {\"failed\":%u,\"cases\":486,\"regions\":648,\"elements\":181440,\"trials\":3}\n",failed);
 if(failed)fatal(5,REGIONS);
#if DT_NODE_HAS_COMPAT(DT_CHOSEN(zephyr_console), sifive_uart0)
 uintptr_t uart=DT_REG_ADDR(DT_CHOSEN(zephyr_console));uint32_t txctrl=sys_read32(uart+8);sys_write32((txctrl&~(0x1ffu<<16))|(1u<<16),uart+8);while(!(sys_read32(uart+0x14)&1))k_yield();k_sleep(K_MSEC(1));
#endif
 __asm__ volatile("fence rw,rw":::"memory");sys_reboot(SYS_REBOOT_COLD);for(;;){}
}
static void controller(void*a,void*b,void*c){(void)a;(void)b;(void)c;if(physical_hart()!=2||logical_cpu()!=2)fatal(6,0);printk("IRIS_H2_CONTROL_READY {\"physical_hart\":2,\"logical_cpu\":2,\"pin\":2,\"scalar_only\":true}\n");k_sem_give(&controller_ready);k_sem_take(&launch,K_FOREVER);
 uint64_t sequence[2]={0,0};for(unsigned gid=0;gid<GROUPS;++gid){const group_t*g=&groups[gid];unsigned next=g->first;
  for(unsigned h=0;h<2;++h)if(g->mask&(1u<<h)){unsigned rid=next++;prepare(rid);tasks[h].rid=rid;tasks[h].seq=++sequence[h];}
  for(unsigned h=0;h<2;++h)if(g->mask&(1u<<h))k_sem_give(&start[h]);
  next=g->first;for(unsigned h=0;h<2;++h)if(g->mask&(1u<<h)){unsigned rid=next++;k_sem_take(&done[h],K_FOREVER);if(tasks[h].ack!=sequence[h]||records[rid].ack!=sequence[h])fatal(7,gid);verify(rid);}
 }
 packet_record_count=REGIONS;__asm__ volatile("fence rw,rw":::"memory");packet_measurements_done=0;__asm__ volatile("fence rw,rw":::"memory");emit();
}
int main(void){iris_uart_profile_report();if(physical_hart()!=0||logical_cpu()!=0)fatal(8,0);
 for(unsigned h=0;h<2;++h){k_sem_init(&start[h],0,1);k_sem_init(&done[h],0,1);}
 for(unsigned h=0;h<3;++h){k_tid_t t=k_thread_create(&threads[h],stacks[h],K_THREAD_STACK_SIZEOF(stacks[h]),h==2?controller:worker,(void*)(uintptr_t)h,0,0,5,0,K_FOREVER);if(k_thread_cpu_pin(t,h))fatal(9,0);k_thread_start(t);}
 k_sem_take(&controller_ready,K_FOREVER);for(unsigned h=0;h<2;++h)k_sem_give(&start[h]);for(unsigned h=0;h<2;++h)k_sem_take(&worker_ready,K_FOREVER);k_sem_give(&launch);k_sem_take(&never,K_FOREVER);return 0;
}
