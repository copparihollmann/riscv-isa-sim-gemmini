#ifndef IRIS_BENCH_RUNTIME_H
#define IRIS_BENCH_RUNTIME_H
#include <stdint.h>
#include <stddef.h>
#ifndef IRIS_HARTS
#define IRIS_HARTS 3
#endif
#define IRIS_CLINT 0x02000000UL
extern volatile uint64_t tohost, fromhost;
extern volatile uint64_t ipi_seen[IRIS_HARTS], timer_seen[IRIS_HARTS];
extern volatile uint64_t expect_illegal[IRIS_HARTS], illegal_seen[IRIS_HARTS];
static inline unsigned hart_id(void) { unsigned long x; __asm__ volatile("csrr %0, mhartid":"=r"(x)); return x; }
static inline uint64_t cycles(void) { uint64_t x; __asm__ volatile("csrr %0, mcycle":"=r"(x)::"memory"); return x; }
static inline uint64_t retired(void) { uint64_t x; __asm__ volatile("csrr %0, minstret":"=r"(x)::"memory"); return x; }
static inline void memory_fence(void) { __asm__ volatile("fence rw,rw" ::: "memory"); }
static inline void send_ipi(unsigned h) { *(volatile uint32_t *)(IRIS_CLINT + h*4) = 1; memory_fence(); }
static inline uint64_t mtime(void) { return *(volatile uint64_t *)(IRIS_CLINT + 0xbff8); }
static inline void set_timer(unsigned h, uint64_t t) { *(volatile uint64_t *)(IRIS_CLINT + 0x4000 + h*8) = t; memory_fence(); }
void putstr(const char *s);
void putuint(uint64_t value);
void barrier(void);
void benchmark_main(unsigned hart);
void finish(unsigned status) __attribute__((noreturn));
void fail(unsigned hart, uint64_t cause, uint64_t pc, uint64_t value) __attribute__((noreturn));
#endif
