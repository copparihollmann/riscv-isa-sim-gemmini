/* Independent public ISA semantic probe. Expected values are literal integer
 * arithmetic results; no measured labels, private kernels or tuned prices. */
typedef unsigned long u64;
extern volatile u64 tohost;
static const struct {u64 a,b,expected[8];} cases[]={
 {0x8000000000000000ul,0x1ul,{0x8000000000000000ul,0x8000000000000000ul,0x0ul,0x0ul,0x0ul,0x0ul,0x0ul,0x0ul}},
 {0xffful,0x7ul,{0x249ul,0x249ul,0x0ul,0x0ul,0x249ul,0x249ul,0x0ul,0x0ul}},
 {0x1ul,0x8000000000000000ul,{0x0ul,0x0ul,0x1ul,0x1ul,0xfffffffffffffffful,0xfffffffffffffffful,0x1ul,0x1ul}},
 {0x0ul,0x0ul,{0xfffffffffffffffful,0xfffffffffffffffful,0x0ul,0x0ul,0xfffffffffffffffful,0xfffffffffffffffful,0x0ul,0x0ul}},
 {0xfffffffffffffff9ul,0x3ul,{0xfffffffffffffffeul,0x5555555555555553ul,0xfffffffffffffffful,0x0ul,0xfffffffffffffffeul,0x55555553ul,0xfffffffffffffffful,0x0ul}},
 {0x8000000000000000ul,0xfffffffffffffffful,{0x8000000000000000ul,0x0ul,0x0ul,0x8000000000000000ul,0x0ul,0x0ul,0x0ul,0x0ul}},
 {0xfffffffffffffffful,0x0ul,{0xfffffffffffffffful,0xfffffffffffffffful,0xfffffffffffffffful,0xfffffffffffffffful,0xfffffffffffffffful,0xfffffffffffffffful,0xfffffffffffffffful,0xfffffffffffffffful}},
 {0xdeadbeef80000000ul,0x12345678fffffffful,{0xfffffffffffffffful,0xcul,0xf0e215687ffffffful,0x439b1438000000cul,0xffffffff80000000ul,0x0ul,0x0ul,0xffffffff80000000ul}},
 {0x12345678fffffffful,0x2ul,{0x91a2b3c7ffffffful,0x91a2b3c7ffffffful,0x1ul,0x1ul,0x0ul,0x7ffffffful,0xfffffffffffffffful,0x1ul}},
 {0x1234567880000000ul,0x0ul,{0xfffffffffffffffful,0xfffffffffffffffful,0x1234567880000000ul,0x1234567880000000ul,0xfffffffffffffffful,0xfffffffffffffffful,0xffffffff80000000ul,0xffffffff80000000ul}},
};
static volatile u64 observed[sizeof(cases)/sizeof(cases[0])][8];
static volatile u64 multiplied[sizeof(cases)/sizeof(cases[0])][8];
static void put(char c){tohost=0x0101000000000000ul|(unsigned char)c;while(tohost){}}
static void text(const char*s){while(*s)put(*s++);}
static void decimal(u64 n){char b[24];unsigned i=0;do{b[i++]=(char)('0'+n%10);n/=10;}while(n);while(i)put(b[--i]);}
__attribute__((noinline)) void kernel_entry(void){
 for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);i++){
  u64 r,p,a=cases[i].a,b=cases[i].b,three=3;
#define OP(n,insn) __asm__ volatile(insn " %0,%1,%2":"=r"(r):"r"(a),"r"(b)); \
 __asm__ volatile("mul %0,%1,%2":"=r"(p):"r"(r),"r"(three)); \
 observed[i][n]=r;multiplied[i][n]=p;
  OP(0,"div");OP(1,"divu");OP(2,"rem");OP(3,"remu");
  OP(4,"divw");OP(5,"divuw");OP(6,"remw");OP(7,"remuw");
#undef OP
 }
}
__attribute__((noinline)) void kernel_complete(void){__asm__ volatile("fence":::"memory");}
int main(void){
 kernel_complete();u64 begin,end;
 __asm__ volatile("csrr %0,mcycle":"=r"(begin)::"memory");
 kernel_entry();kernel_complete();
 __asm__ volatile("csrr %0,mcycle":"=r"(end)::"memory");
 unsigned errors=0;
 for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);i++)for(unsigned j=0;j<8;j++){
  if(observed[i][j]!=cases[i].expected[j])errors++;
  if(multiplied[i][j]!=cases[i].expected[j]*3ul)errors++;
 }
 text("INTEGER_DIVIDER cycles=");decimal(end-begin);text(" checked=160 mismatches=");decimal(errors);text("\n");
 return errors?1:0;
}
