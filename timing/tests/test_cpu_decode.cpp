#include "cpu_decode.hpp"
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
static void check(bool value,const char* message) { if(!value) throw std::runtime_error(message); }
static std::uint64_t fp(unsigned f7,unsigned f3=0,unsigned rs2=4) {
  return (std::uint64_t(f7)<<25)|(std::uint64_t(rs2)<<20)|(3u<<15)|(f3<<12)|(2u<<7)|0x53u;
}
static std::uint64_t csr(unsigned address,unsigned f3,unsigned rd,unsigned rs1) {
  return (address<<20)|(rs1<<15)|(f3<<12)|(rd<<7)|0x73u;
}
int main() {
  using spike_timing::decode_cpu;
  for (const auto &encoding : spike_timing::bitmanip_encodings) {
    const auto bits = encoding.match | (2u << 7) | (3u << 15);
    const auto decoded = decode_cpu(bits);
    check(decoded.known && std::string(decoded.kind)=="cpu.bitmanip", "known Zba/Zbb/Zbs encoding needs a distinct price class");
    check(decoded.read_count>=1 && decoded.reads[0]==3 && decoded.write_count==1 && decoded.writes[0]==2,
          "bitmanip must retain its actual input and output registers");
  }
  const auto unary=decode_cpu(MATCH_CPOP | (2u<<7) | (3u<<15));
  check(unary.read_count==1,"encoded bitmanip function must not become a spurious input register");
  const auto binary=decode_cpu(MATCH_SH2ADD | (2u<<7) | (3u<<15) | (4u<<20));
  check(binary.read_count==2 && binary.reads[1]==4,"binary bitmanip needs both inputs");
  check(!decode_cpu(MATCH_CLMUL | (2u<<7) | (3u<<15)).known,
        "an unimplemented extension sharing the integer opcode must refuse");
  check(!decode_cpu(0xfe00101bu).known,"reserved word-immediate encoding must refuse");
  for(unsigned format: {2u,3u}) {
    auto load=decode_cpu((3u<<15)|(format<<12)|0x07u);
    check(load.known && load.read_count==1 && load.reads[0]==3 && load.write_count==1 && load.writes[0]==32,
          "scalar FLW/FLD must write f0 rather than discard it as x0");
    check(load.fp_width==(format==2 ? 32u : 64u),"scalar load precision must match its width encoding");
    check(load.floating_register_operands,"scalar FP bank must be explicit for execution-domain checks");
    check(load.memory_address_register==3,"load address must be distinct from loaded data");
    auto store=decode_cpu((4u<<20)|(3u<<15)|(format<<12)|0x27u);
    check(store.fp_width==(format==2 ? 32u : 64u),"scalar store precision must match its width encoding");
    check(store.known && store.read_count==2 && store.reads[1]==36,"scalar FSW/FSD must read FPR input");
    check(store.memory_address_register==3,"store address must be distinct from stored data");
  }
  for(unsigned format: {0u,1u,4u,5u,6u,7u}) {
    check(!decode_cpu((1u<<25)|(3u<<15)|(format<<12)|0x07u).known,"non-scalar-S/D load must be unknown");
    check(!decode_cpu((1u<<25)|(3u<<15)|(format<<12)|0x27u).known,"non-scalar-S/D store must be unknown");
  }
  for(unsigned encoding: {(1u<<13), (5u<<13), (1u<<13)|(2u<<7)|2u, (5u<<13)|(3u<<2)|2u})
    check(decode_cpu(encoding).fp_width==64,"RV64 compressed FP loads/stores must retain D precision");
  auto dynamic=decode_cpu(fp(0,7));
  check(dynamic.known && std::string(dynamic.kind)=="cpu.fp_add" && dynamic.reads_rounding_mode && dynamic.accumulates_fflags,
        "dynamic floating arithmetic must wait for rounding mode and accumulate flags");
  check(dynamic.fp_width==32,"single arithmetic must retain S precision");
  auto fixed=decode_cpu(fp(1));
  check(fixed.fp_width==64,"double arithmetic must retain D precision");
  check(fixed.known && !fixed.reads_rounding_mode && fixed.accumulates_fflags,"static rounding needs no frm dependency");
  for(unsigned rounding: {5u,6u}) check(!decode_cpu(fp(0,rounding)).known,"reserved rounding mode must refuse");
  check(std::string(decode_cpu(fp(4)).kind)=="cpu.fp_subtract","subtraction needs its own price class");
  for(unsigned f7: {16u,17u}) {
    auto sign=decode_cpu(fp(f7,2));
    check(sign.known && std::string(sign.kind)=="cpu.fp_sign" && !sign.accumulates_fflags && !sign.reads_rounding_mode,
          "sign injection must not pretend to be rounded arithmetic");
    check(!decode_cpu(fp(f7,3)).known,"reserved sign form must refuse");
  }
  for(unsigned f7: {20u,21u}) {
    auto min=decode_cpu(fp(f7,1));
    check(min.known && std::string(min.kind)=="cpu.fp_minmax" && min.accumulates_fflags && !min.reads_rounding_mode,
          "min/max exceptions and no rounding dependency must remain explicit");
  }
  auto conversion=decode_cpu(fp(32,7,1));
  check(conversion.known && conversion.read_count==1 && conversion.reads_rounding_mode && conversion.accumulates_fflags &&
          std::string(conversion.kind)=="cpu.fp_convert","format conversion must not read an encoded source format as FPR");
  check(conversion.fp_width==32 && conversion.fp_source_width==64,"D-to-S conversion must retain both precisions");
  auto widen=decode_cpu(fp(33,0,0));
  check(widen.known && widen.fp_width==64 && widen.fp_source_width==32,"S-to-D conversion must retain both precisions");
  check(!decode_cpu(fp(32,0,2)).known,"half conversion input must refuse");
  check(decode_cpu(fp(44,0,0)).known && !decode_cpu(fp(44,0,1)).known,"sqrt must enforce reserved rs2 field");
  check(!decode_cpu(fp(2)).known && !decode_cpu(fp(3)).known,"half/quad arithmetic must not become FP add");
  check(!decode_cpu(fp(96,0,4)).known,"unsupported integer conversion type must refuse");
  auto toint=decode_cpu(fp(96,7,3));
  check(toint.known && toint.reads[0]==35 && toint.writes[0]==2 && toint.reads_rounding_mode,"FP-to-integer operand banks must differ");
  auto fromint=decode_cpu(fp(104,0,2));
  check(fromint.known && fromint.reads[0]==3 && fromint.writes[0]==34,"integer-to-FP operand banks must differ");
  auto move=decode_cpu(fp(112,0,0));
  auto classify=decode_cpu(fp(113,1,0));
  check(move.known && std::string(move.kind)=="cpu.fp_move_to_int" && !move.accumulates_fflags,
        "bit moves must not use conversion or exception semantics");
  check(classify.known && std::string(classify.kind)=="cpu.fp_classify" && !classify.accumulates_fflags,
        "classification must not use conversion or exception semantics");
  check(!decode_cpu(fp(112,0,1)).known,"extended move source operands need their own implementation");
  for(unsigned major: {0x43u,0x47u,0x4bu,0x4fu}) {
    auto fma=decode_cpu((5u<<27)|(4u<<20)|(3u<<15)|(7u<<12)|(2u<<7)|major);
    check(fma.known && fma.read_count==3 && fma.reads[2]==37 && fma.accumulates_fflags && fma.reads_rounding_mode,
          "fused operations need all operands and FP state dependencies");
    check(fma.fp_width==32,"single FMA precision must match format");
    check(decode_cpu((1u<<25)|major).fp_width==64,"double FMA precision must match format");
    check(!decode_cpu((2u<<25)|major).known,"unsupported FMA formats must refuse");
  }
  auto flags=decode_cpu(csr(1,2,1,0));
  check(flags.reads_fflags && !flags.writes_fflags && !flags.reads_rounding_mode,"frflags must only observe flags");
  auto mode=decode_cpu(csr(2,6,1,0));
  check(mode.reads_rounding_mode && !mode.writes_rounding_mode && mode.read_count==0,
        "zero immediate CSR set must not write state or read a GPR");
  auto setall=decode_cpu(csr(3,1,0,1));
  check(setall.writes_fflags && setall.writes_rounding_mode && !setall.reads_fflags && !setall.reads_rounding_mode,
        "CSRRW x0 must overwrite aliases without reporting an unused CSR read");
  auto clear=decode_cpu(csr(1,3,1,1));
  check(clear.reads_fflags && clear.writes_fflags && !clear.accumulates_fflags,"CSR flag updates are destructive rather than sticky updates");
  check(!decode_cpu(csr(3,4,1,1)).known,"reserved CSR opcode must refuse");
  check(decode_cpu(csr(0xc00,2,1,0)).counter_read,"counter boundary detection must remain compatible");
  check(decode_cpu((7u<<20)|0x23u).memory_address_register==0,
        "x0-based store must not use its data register as an address dependency");
  check(decode_cpu((5u<<15)|0x2fu).memory_address_register==5,"atomic address must be explicit");
  check(decode_cpu((5u<<13)|(3u<<2)|2u).memory_address_register==2,
        "compressed stack store must retain the stack address dependency");
  std::cout<<"scalar FP/FCSR decoder controls passed\n";
}
