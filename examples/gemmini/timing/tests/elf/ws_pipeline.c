/* Public independent protocol probe: raw ISA, no reference compiler/kernel.
 * Completion uses architectural FENCE: synthetic Spike funct127 is not RTL ISA. */
typedef unsigned long u64;
typedef signed char i8;
typedef int i32;
extern volatile u64 tohost;
#ifndef TILES
#define TILES 8
#endif
static volatile i8 a[256] __attribute__((aligned(64)));
static volatile i8 b[256] __attribute__((aligned(64)));
static volatile i32 output[TILES*256] __attribute__((aligned(64)));
#define COMMAND(f,x,y) __asm__ volatile(".insn r 0x7b, 3, %c2, x0, %0, %1"::"r"((u64)(x)),"r"((u64)(y)),"i"(f):"memory")
static u64 tile(unsigned p) {return p | (16ul<<32) | (16ul<<48);}
static void put(char c) {tohost=0x0101000000000000ul|(unsigned char)c;while(tohost){}}
static void text(const char *s) {while(*s)put(*s++);}
static void decimal(u64 n) {char b[24];unsigned i=0;do {b[i++]=(char)('0'+n%10);n/=10;}while(n);while(i)put(b[--i]);}
__attribute__((noinline)) void kernel_entry(void) {
 for(unsigned n=0;n<TILES;n++) {
  COMMAND(6,tile(4096),tile(0x80000000u+n*16));
  COMMAND(4,tile(0),tile(0xffffffffu));
#ifdef FENCED
  __asm__ volatile("fence":::"memory");
#endif
 }
 for(unsigned n=0;n<TILES;n++) {
#ifdef FENCE_READOUT
  __asm__ volatile("fence":::"memory");
#endif
  COMMAND(3,output+n*256,tile(0xa0000000u+n*16));
#ifdef FENCE_READOUT
  __asm__ volatile("fence":::"memory");
#endif
 }
}
__attribute__((noinline)) void kernel_complete(void) {__asm__ volatile("fence":::"memory");}
int main(void) {
 const u64 one=0x3f800000ul;
 for(unsigned i=0;i<256;i++){a[i]=(i8)((int)(i*3%7)-3);b[i]=(i8)((int)(i*5%9)-4);}
 for(unsigned i=0;i<TILES*256;i++)output[i]=0x6d6d6d6d;
 COMMAND(0,2ul|(1ul<<2),(one<<32)|64);COMMAND(0,2,(one<<32)|64);
 COMMAND(0,1ul|(1ul<<8)|(16ul<<16)|(one<<32),16);
 COMMAND(2,a,tile(0));COMMAND(2,b,tile(4096));
 COMMAND(0,4ul|(1ul<<16)|(one<<32),1ul<<48);
 kernel_complete();
 u64 begin,end;__asm__ volatile("csrr %0,mcycle":"=r"(begin)::"memory");
 kernel_entry();kernel_complete();
 __asm__ volatile("csrr %0,mcycle":"=r"(end)::"memory");
 unsigned errors=0;
 for(unsigned n=0;n<TILES;n++)for(unsigned i=0;i<16;i++)for(unsigned j=0;j<16;j++){
  i32 expected=0;for(unsigned k=0;k<16;k++)expected+=(i32)a[i*16+k]*(i32)b[k*16+j];
  if(output[n*256+i*16+j]!=expected)errors++;
 }
 text("WS_PIPELINE cycles=");decimal(end-begin);text(" checked=");decimal(TILES*256);text(" mismatches=");decimal(errors);text("\n");
 return errors?1:0;
}
