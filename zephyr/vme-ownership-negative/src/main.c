#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <stdint.h>
extern void z_iris_vme_tiles_save(void *);
static struct k_thread worker;
K_THREAD_STACK_DEFINE(stack,8192);
K_SEM_DEFINE(never,0,1);
static uint32_t cells[4][32][32];
static void omitted(void *a,void *b,void *c) {
  (void)a;(void)b;(void)c;
  /* Deliberately omit iris_vme_enable and all tile initialization. A fresh
   * simulation must reject the first row read. This is a negative corpus ELF,
   * not a legal application or an attempt to initialize tile state in Spike. */
  z_iris_vme_tiles_save(cells);
  printk("IRIS_FATAL unexpected success reading uninitialized matrix tiles\n");k_panic();
}
int main(void) {
  k_tid_t t=k_thread_create(&worker,stack,K_THREAD_STACK_SIZEOF(stack),omitted,NULL,NULL,NULL,5,K_FP_REGS,K_FOREVER);
  if(k_thread_cpu_pin(t,0))k_panic();k_thread_start(t);k_sem_take(&never,K_FOREVER);return 1;
}
