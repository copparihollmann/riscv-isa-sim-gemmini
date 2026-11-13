#include "runtime.h"
#include "vme.h"
// First native-bridge capability: initialized integer compute on hart 0.
// No vector memory, FP operations, column moves, IPIs or timer interrupts.
static volatile uint64_t peer_values[IRIS_HARTS];
static void source_drain(void) { __asm__ volatile("fence rw,rw" ::: "memory"); }
static void number(uint64_t value) { putstr(" "); putuint(value); }
void benchmark_main(unsigned hart) {
  // Preserve the unchanged common CRT; make this guest's no-IRQ admission
  // explicit after it has established the real board UART and trap vector.
  __asm__ volatile("csrw mie,zero\n\tcsrw vstart,zero\n\tcsrw vxrm,zero\n\tcsrw frm,zero" ::: "memory");
  peer_values[hart] = 0x71 + hart;
  barrier();
  if (hart == 0) {
    uint64_t rvv_result, result, scalar_sum;
    __asm__ volatile("vsetivli zero,1,e8,m1,ta,ma\n\tvmv.v.i v4,7\n\tvadd.vi v4,v4,1\n\tvmv.x.s %0,v4"
                     : "=r"(rvv_result) :: "memory");
    source_drain();
    if (rvv_result != 8) fail(hart,0x4c495631,0,rvv_result);
    vme_vsettnt_e8w4(32);
    vme_vsettm(32);
    vme_vsettk(1);
    VME_VTZERO(0);
    __asm__ volatile("vmv.v.i v8,2\n\tvmv.v.i v16,3" ::: "memory");
    source_drain();
    uint64_t before = cycles(), instructions_before = retired();
    VME_MM_U_U(0,8,16);
    __asm__ volatile("li t0,0\n\t.rept 64\n\taddi t0,t0,1\n\t.endr\n\tmv %0,t0"
                     : "=r"(scalar_sum) :: "t0","memory");
    uint64_t after_scalar = cycles(), instructions_after_scalar = retired();
    // Scalar retirement alone is not completion of the decoupled unit. The
    // native caller must honor the source CPU fence's real unit busy gates and
    // retain all physical tails; it may not replace this by a fitted delay.
    source_drain();
    uint64_t after_drain = cycles();
    vme_vsettnt_e32w1(32);
    VME_VTMV_V_T(24,vme_tss(0,VME_TSS_ROW,0));
    source_drain();
    __asm__ volatile("vmv.x.s %0,v24" : "=r"(result) :: "memory");
    source_drain();
    uint64_t after_readout = cycles();
    if (result != 6 || scalar_sum != 64 || peer_values[1] != 0x72 || peer_values[2] != 0x73)
      fail(hart,0x4c495632,scalar_sum,result);
    putstr("IRIS_SATURN_LIVE_VALUES");number(rvv_result);number(result);number(scalar_sum);putstr("\n");
    putstr("IRIS_SATURN_LIVE_TIME");number(before);number(after_scalar);number(after_drain);number(after_readout);number(instructions_before);number(instructions_after_scalar);putstr("\n");
  }
  barrier();
  if (hart == 0) { putstr("IRIS_SATURN_LIVE_DONE 3\n"); finish(0); }
  for (;;) __asm__ volatile("wfi");
}
