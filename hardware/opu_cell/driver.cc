#include "VOuterCell.h"
#include <verilated.h>
#include <array>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include "fp8_cases.hpp"

class Check {
 public:
  VOuterCell top;
  std::array<uint32_t,16> expected{};
  uint64_t int_cases=0, fp8_cases_count=0, fp8_macs=0, scans=0;
  Check() {
    top.clock=0;top.reset=1;quiet();
    for(unsigned i=0;i<3;++i)tick();
    top.reset=0;
    // MRF storage is unreset. Define every tested entry explicitly.
    for(unsigned i=0;i<16;++i)load(i,0);
    scan();
  }
  void quiet() {top.io_macc=0;top.io_mvin=0;top.io_zero=0;top.io_fp8=0;}
  void tick() {top.clock=0;top.eval();top.clock=1;top.eval();top.clock=0;top.eval();}
  uint32_t read(unsigned index) {top.io_mrf_idx=index;top.eval();return top.io_out;}
  void equal(unsigned index,uint32_t want,const char* why) {
    const auto got=read(index);
    if(got!=want)throw std::runtime_error(std::string(why)+" index="+std::to_string(index)+" got="+std::to_string(got)+" expected="+std::to_string(want));
  }
  void load(unsigned index,uint32_t value) {
    quiet();top.io_mrf_idx=index;top.io_mvin=1;top.io_mvin_data=value;tick();quiet();
    expected[index]=value;equal(index,value,"mvin");
  }
  void scan() {quiet();for(unsigned i=0;i<16;++i)equal(i,expected[i],"entry isolation");++scans;}
  void integer_case(unsigned a,unsigned b,bool sa,bool sb,uint32_t acc,unsigned index) {
    load(index,acc);top.io_mrf_idx=index;top.io_in_l=a;top.io_in_t=b;top.io_signed_l=sa;top.io_signed_t=sb;
    top.io_macc=1;tick();quiet();
    const int64_t lhs=sa && a>=128 ? int(a)-256 : int(a);
    const int64_t rhs=sb && b>=128 ? int(b)-256 : int(b);
    expected[index]=uint32_t(uint64_t(acc)+uint64_t(lhs*rhs));
    equal(index,expected[index],"integer wrapping MAC");++int_cases;
  }
  void issue8(unsigned index,unsigned a,unsigned b,unsigned fa,unsigned fb,unsigned rm) {
    quiet();top.io_mrf_idx=index;top.io_fp8=1;top.io_in_l=a;top.io_in_t=b;
    top.io_e5m2_l=fa;top.io_e5m2_t=fb;top.io_rm=rm;top.io_macc=1;tick();++fp8_macs;
    // Keep rm stable while this operation is in flight.
  }
  void step8(unsigned index,unsigned a,unsigned b,unsigned fa,unsigned fb,unsigned rm) {
    issue8(index,a,b,fa,fb,rm);quiet();tick();tick();
  }
  void fp8_case(const FP8Case& c,unsigned index) {
    load(index,c.acc);
    for(unsigned k=0;k<c.tk;++k)step8(index,c.a[k],c.b[k],c.fa,c.fb,c.rm);
    expected[index]=c.want;equal(index,c.want,"sequential FP8/FP32 FMA");++fp8_cases_count;
  }
  void priority() {
    for(unsigned i=0;i<16;++i) {
      load(i,0x7fffffff);top.io_zero=1;top.io_mvin=1;top.io_mvin_data=123;
      top.io_in_l=128;top.io_in_t=2;top.io_signed_l=1;top.io_signed_t=0;top.io_macc=1;tick();quiet();
      expected[i]=0x7ffffeff;equal(i,expected[i],"int MAC over zero/mvin priority");
      top.io_zero=1;top.io_mvin=1;tick();quiet();expected[i]=0;equal(i,0,"zero over mvin priority");
    }
  }
  void latency() {
    load(0,0);issue8(0,0x38,0x38,0,0,0);equal(0,0,"FP8 acceptance edge");
    quiet();tick();equal(0,0,"FP8 first in-flight edge");tick();expected[0]=0x3f800000;
    equal(0,expected[0],"FP8 write two edges after acceptance");
  }
  void parallel_entries() {
    std::array<const FP8Case*,16> batch{};unsigned n=0;uint64_t batches=0;
    for(const auto& c:fp8_cases) {
      if(c.rm || c.tk!=1)continue;
      batch[n++]=&c;
      if(n!=16)continue;
      for(unsigned i=0;i<16;++i)load(i,batch[i]->acc);
      for(unsigned i=0;i<16;++i) {
        const auto& c=*batch[i];issue8(i,c.a[0],c.b[0],c.fa,c.fb,0);expected[i]=c.want;
      }
      quiet();tick();tick();scan();n=0;++batches;
    }
    if(n || batches!=32)throw std::runtime_error("unexpected independent-entry corpus shape");
  }
};

static uint32_t little32(const uint8_t* p) {return uint32_t(p[0])|uint32_t(p[1])<<8|uint32_t(p[2])<<16|uint32_t(p[3])<<24;}
int main(int argc,char** argv) {
  try {
    if(argc!=2)throw std::runtime_error("binary exhaustive FP8 corpus required");
    Verilated::commandArgs(argc,argv);Check test;
    test.priority();test.latency();
    const uint32_t seeds[]={0,1,0xffffffff,0x7fffffff,0x80000000,0x12345678,0xfedcba98};
    for(unsigned sa=0;sa<2;++sa)for(unsigned sb=0;sb<2;++sb)
      for(unsigned a=0;a<256;++a)for(unsigned b=0;b<256;++b) {
        test.integer_case(a,b,sa,sb,seeds[(a+3*b+sa+2*sb)%7],(a^b^sa^(sb<<1))&15);
        if((b&255)==255)test.scan();
      }
    for(unsigned i=0;i<std::size(fp8_cases);++i)test.fp8_case(fp8_cases[i],i&15);
    std::ifstream input(argv[1],std::ios::binary);std::array<uint8_t,20> bytes{};uint64_t records=0;
    while(input.read(reinterpret_cast<char*>(bytes.data()),bytes.size())) {
      FP8Case c{};for(unsigned i=0;i<4;++i){c.a[i]=bytes[i];c.b[i]=bytes[4+i];}
      c.fa=bytes[8];c.fb=bytes[9];c.tk=bytes[10];c.rm=bytes[11];c.acc=little32(&bytes[12]);c.want=little32(&bytes[16]);
      if(c.fa>1 || c.fb>1 || c.tk!=1 || c.rm!=0)throw std::runtime_error("invalid exhaustive corpus record");
      test.fp8_case(c,records&15);++records;
    }
    if(!input.eof() || input.gcount()!=0 || records!=262144)throw std::runtime_error("truncated/excess corpus");
    test.parallel_entries();test.scan();
    std::cout<<"{\"status\":\"passed_saved_opu_cell\",\"integer_mac_cases\":"<<test.int_cases
      <<",\"fp8_sequences\":"<<test.fp8_cases_count<<",\"fp8_mac_operations\":"<<test.fp8_macs
      <<",\"exhaustive_fp8_pairs\":"<<records<<",\"entry_scans\":"<<test.scans
      <<",\"parallel_entry_batches\":32,\"priority_entries\":16,\"latency_two_edges_after_acceptance\":true}\n";
    test.top.final();return 0;
  } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
}
