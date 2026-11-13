#include <zephyr/arch/riscv/iris_flush_frontier.h>
static uint32_t diag_sequence[3];
static struct k_thread diag_thread;
K_THREAD_STACK_DEFINE(diag_stack,4096);
K_SEM_DEFINE(diag_joined,0,1);
static void diag_mark(unsigned channel,unsigned stage,unsigned job){
 uint64_t word=((uint64_t)++diag_sequence[channel]<<32)|((uint64_t)hart()<<28)|((uint64_t)(phase&15)<<24)|((uint64_t)(job&255)<<16)|stage;
 iris_frontier_app_stamp(channel,word);
}
static void diag_arm_task(void*a,void*b,void*c){
 (void)a;(void)b;(void)c;if(hart()!=1||iris_frontier_arm(3000,iris_diag_watchdog_enabled))fail(0,90);k_sem_give(&diag_joined);
}
