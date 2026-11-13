// Execute actual pinned Spike handlers; this is not an independent RTL oracle.
#include "processor.h"
#include "simif.h"
#include "trap.h"
#include "mmu.h"
#include "devices.h"
#include <array>
#include <algorithm>
#include <cstring>
#include "encoding.h"
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <csignal>
#include <execinfo.h>
#include "decoder_cases.hpp"
#include "fp8_cases.hpp"
#include "iris_fp8.hpp"

static const char* compute_isa = "rv64gcv_zvl256b_zfh_zvfh_zvfofp8min_zvfbfa_zvfbfmin_zvt32t_zvti8i32mm_zvtofp8fmm";
static const char* dma_isa = "rv64gcv_zvl256b_zfh_zvfh_zvbb";
struct Fixture : simif_t {
  cfg_t cfg;
  alignas(4096) std::array<char,4096> ram{}, scratch{};
  std::map<size_t, processor_t*> harts;
  std::vector<std::unique_ptr<processor_t>> storage;
  Fixture(bool iris) {
    cfg.isa = dma_isa; cfg.iris_vme = iris; cfg.hartids = {0, 1, 2};
    for (unsigned i = 0; i < 3; ++i) {
      auto p = std::make_unique<processor_t>(i < 2 ? compute_isa : dma_isa,
          "MSU", &cfg, this, i, false, nullptr, std::cerr);
      // Reference Zvt needs MS; Iris only relies on VS as the RTL does.
      p->get_state()->mstatus->write(MSTATUS_VS | MSTATUS_FS | (iris ? 0 : SSTATUS_MS));
      // Numerical handler fixtures establish configured software input state.
      // This is an explicit precondition, not a hardware-reset-zero claim.
      p->VU.vstart->write(0);
      harts[i] = p.get(); storage.push_back(std::move(p));
    }
  }
  char* addr_to_mem(reg_t addr) override {
    if(addr>=0x580000000ULL && addr<0x580001000ULL)return scratch.data()+addr-0x580000000ULL;
    return addr >= 0x80000000 && addr < 0x80001000 ? ram.data() + (addr-0x80000000) : nullptr;
  }
  bool mmio_load(reg_t,size_t,uint8_t*) override { return false; }
  bool mmio_store(reg_t,size_t,const uint8_t*) override { return false; }
  void proc_reset(unsigned) override {}
  const cfg_t& get_cfg() const override { return cfg; }
  const std::map<size_t,processor_t*>& get_harts() const override { return harts; }
  const char* get_symbol(uint64_t) override { return nullptr; }
  processor_t& p(unsigned id=0) { return *storage.at(id); }
};
void check(bool value, const std::string& msg) {
  if (!value) throw std::runtime_error(msg);
}
static uint32_t last_bits=0,last_hart=0;
void exec(processor_t& p, uint32_t bits) {
  if (!p.VU.iris_mode && ((bits & 0x7f) == 0x77 || ((bits & 0x707f) == 0x6057))) bits |= 1u << 25;
  last_bits=bits;last_hart=p.get_id();
  insn_t insn(bits);
  p.decode_for_model(insn)(&p, insn, 0x80000000);
}
void config(processor_t& p,unsigned sew,unsigned widen,unsigned tn,unsigned tm,unsigned tk,bool alt=false) {
  unsigned code = widen==4 ? 3 : widen==2 ? 2 : widen==1 ? 1 : 0;
  auto& x = p.get_state()->XPR;
  x.write(6,code); x.write(7,((sew==32?2:sew==16?1:0)<<3)|(alt?256:0));
  // Upstream Zvt's published pin derives LMUL using the previous SEW.
  exec(p, MATCH_MSETMTYPE | (7<<20) | (6<<15));
  if (!p.VU.iris_mode) exec(p, MATCH_MSETMTYPE | (7<<20) | (6<<15));
  x.write(6,tn); exec(p,MATCH_MSETTN|(6<<15)|(5<<7));
  x.write(6,tm); exec(p,MATCH_MSETTM|(6<<15)|(5<<7));
  x.write(6,tk); exec(p,MATCH_MSETTK|(6<<15)|(5<<7));
}
void illegal(processor_t& p,uint32_t bits) {
  bool seen=false;
  try { exec(p,bits); } catch (const trap_t& t) { seen=t.cause()==CAUSE_ILLEGAL_INSTRUCTION; }
  check(seen,"expected illegal instruction");
}
void arithmetic(Fixture& f,bool alt,unsigned tile,bool signed_a) {
  auto& p=f.p();
  config(p,8,4,7,5,4,alt);
  check(p.VU.vl->read()==7 && p.VU.tm==5 && p.VU.tk==4,"shape configuration");
  exec(p,MATCH_VTZERO|(tile<<10));
  for (unsigned k=0;k<4;k++) for(unsigned i=0;i<32;i++) {
    p.VU.elt<uint8_t>(8+2*k,i,true)=uint8_t(127+31*k+17*i);
    p.VU.elt<uint8_t>(16+2*k,i,true)=uint8_t(201+13*k+29*i);
  }
  const uint32_t mm=(signed_a?MATCH_VTMMS_TVV:MATCH_VTMMU_TVV)|(8<<20)|(16<<15)|(tile<<10);
  for(unsigned repeat=0;repeat<3;repeat++) exec(p,mm);
  for(unsigned m=0;m<5;m++) for(unsigned n=0;n<7;n++) {
    int64_t expected=0;
    for(unsigned k=0;k<4;k++) {
      uint8_t a=uint8_t(127+31*k+17*m), b=uint8_t(201+13*k+29*n);
      expected+=(signed_a?int64_t(int8_t(a)):a)*(alt?int64_t(int8_t(b)):b);
    }
    check(p.VU.mt_elt<uint32_t>(tile*4,m,n)==uint32_t(expected*3),"int8 signedness/accumulation");
  }
}
int main(int argc,char** argv) {
  std::signal(SIGABRT,[](int){void* frames[32];int n=backtrace(frames,32);backtrace_symbols_fd(frames,n,2);std::_Exit(134);});
  try {
    const bool iris=argc>1 && std::string(argv[1])=="--iris";
    Fixture f(iris); auto& p=f.p();
    if(iris) {
      bool invalid_dma=false;
      try { processor_t invalid(compute_isa,"MSU",&f.cfg,&f,2,false,nullptr,std::cerr); }
      catch(const std::invalid_argument&){invalid_dma=true;}
      check(invalid_dma,"Iris rejects contradictory VME ISA on hart2");
      auto& dma=f.p(2);
      dma.get_state()->XPR.write(6,8);
      exec(dma,MATCH_VSETVLI|(0xc0<<20)|(6<<15)|(5<<7));
      for(unsigned i=0;i<8;i++)dma.get_mmu()->store<uint8_t>(0x80000000+i,17*i);
      dma.get_state()->XPR.write(6,0x80000000);
      exec(dma,MATCH_VLE8_V|(1<<25)|(6<<15)|(8<<7));
      dma.get_state()->XPR.write(6,0x80000020);
      exec(dma,MATCH_VSE8_V|(1<<25)|(6<<15)|(8<<7));
      for(unsigned i=0;i<8;i++)check(dma.get_mmu()->load<uint8_t>(0x80000020+i)==17*i,"verified hart2 vector memcpy");
      exec(dma,MATCH_VADD_VV|(1<<25)|(8<<20)|(8<<15)|(8<<7));
      for(unsigned i=0;i<8;i++)check(dma.VU.elt<uint8_t>(8,i)==uint8_t(34*i),"hart2 source-verified integer arithmetic");
      exec(dma,MATCH_VMV_V_I|(1<<15)|(8<<7));
      for(unsigned i=0;i<8;i++)check(dma.VU.elt<uint8_t>(8,i)==1,"hart2 source-verified vector move");
      for(const auto& item:decoder_cases) {
        std::vector<insn_func_t> group{p.decode_for_model(insn_t(item.match))};
        if ((item.match&0x7f)==0x77) group.push_back(p.decode_for_model(insn_t(item.match|128)));
        for(unsigned bit=0;bit<32;bit++) {
          auto handler=p.decode_for_model(insn_t(item.match^(1u<<bit)));
          bool same=std::find(group.begin(),group.end(),handler)!=group.end();
          check(same==((item.mask&(1u<<bit))==0),std::string("RTL decoder single-bit predicate ")+item.name);
        }
        uint32_t rng=0x6d2b79f5;
        for(unsigned trial=0;trial<1024;trial++) {
          rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;
          auto handler=p.decode_for_model(insn_t(item.match|(rng&~item.mask)));
          check(std::find(group.begin(),group.end(),handler)!=group.end(),std::string("RTL decoder ignored-field combination ")+item.name);
        }
      }
      for(uint32_t setter:{uint32_t(MATCH_MSETTN),uint32_t(MATCH_MSETTM),uint32_t(MATCH_MSETTK)}) {
        p.get_state()->XPR.write(6,17);
        exec(p,MATCH_VSETVLI|(0xc0<<20)|(6<<15)|(5<<7));
        check(!p.VU.vill && p.VU.widen==0 && p.VU.vl->read()==17,"ordinary RVV before unconfigured setter");
        exec(p,setter|(6<<15)|(5<<7));
        check(p.VU.vill && p.VU.vl->read()==0 && p.get_state()->XPR[5]==0,"unconfigured matrix setter must invalidate");
      }
      p.get_state()->XPR.write(6,0);p.get_state()->XPR.write(7,0xd0);p.get_state()->XPR.write(5,999);
      exec(p,MATCH_MSETMTYPE|(7<<20)|(6<<15)|(5<<7));
      check(!p.VU.vill && p.VU.widen==0 && p.VU.vl->read()==0 && p.get_state()->XPR[5]==0,"widen0 standard vtype and rd clobber");
      p.get_state()->XPR.write(5,999);
      exec(p,MATCH_MSETMTYPEI|(3<<15)|(5<<7));
      check(p.get_state()->XPR[5]==0,"immediate mtype rd clobber");
      config(p,32,1,32,32,1,true);
      check(!p.VU.vill && p.VU.altfmt && (p.VU.vtype->read()&256),"matrix e32 altfmt remains legal");
      config(p,8,4,32,32,4);check(p.VU.vflmul==1,"e8 LMUL1");
      config(p,32,1,32,32,1);check(p.VU.vflmul==4,"e8 to e32 LMUL4");
      config(p,8,4,32,32,4);check(p.VU.vflmul==1,"e32 to e8 LMUL1");
    }
    exec(p,MATCH_MSETMTYPEI|(3<<15));
    if (!iris) exec(p,MATCH_MSETMTYPEI|(3<<15));
    check(p.VU.widen==4 && p.VU.tm==0 && p.VU.tk==0,"immediate mtype configuration");
    for(unsigned a=0;a<2;a++) for(unsigned b=0;b<2;b++) arithmetic(f,b,a*2+b,a);
    // Clamp all dimensions at TE=32, KMAX=4.
    config(p,8,4,999,999,999);
    check(p.VU.vl->read()==32 && p.VU.tm==32 && p.VU.tk==4,"edge clamp");
    // e32 row writes and column reads exercise the actual tile layout.
    config(p,32,1,32,32,1);
    exec(p,MATCH_VTZERO);
    for(unsigned row=0;row<32;row++) {
      for(unsigned col=0;col<32;col++) p.VU.elt<uint32_t>(8,col,true)=row*100+col;
      p.get_state()->XPR.write(6,row);
      exec(p,MATCH_VTMV_T_V|(8<<20)|(6<<15));
    }
    p.get_state()->XPR.write(6,(iris?0:(1<<24))|9);
    exec(p,MATCH_VTMV_V_T|(6<<15)|(12<<7));
    for(unsigned row=0;row<32;row++) check(p.VU.elt<uint32_t>(12,row)==(iris?900+row:row*100+9),"tile transpose move");
    // Per-hart state must remain isolated.
    config(f.p(1),32,1,32,32,1);exec(f.p(1),MATCH_VTZERO);
    check(p.VU.mt_elt<uint32_t>(0,3,9)==309,"hart tile isolation");
    // Every Iris VME opcode must refuse the DMA hart.
    for(uint32_t opcode:{uint32_t(MATCH_MSETMTYPE),uint32_t(MATCH_MSETMTYPEI),uint32_t(MATCH_MSETTN),uint32_t(MATCH_MSETTM),uint32_t(MATCH_MSETTK),uint32_t(MATCH_VTMV_V_T),uint32_t(MATCH_VTMV_T_V),uint32_t(MATCH_VTZERO),uint32_t(MATCH_VTDISCARD),uint32_t(MATCH_VTMMS_TVV),uint32_t(MATCH_VTMMU_TVV)}) illegal(f.p(2),opcode);
    // The same CLINT implementation used by Spike: per-hart IPI and timer compare.
    clint_t clint(&f,1000000,false); // Synthetic test frequency, not a hardware claim.
    uint32_t ipi=1;
    check(clint.store(4,4,reinterpret_cast<uint8_t*>(&ipi)),"CLINT MSIP store");
    check((f.p(1).get_state()->mip->read() & MIP_MSIP)!=0,"hart1 IPI delivery");
    check((f.p(0).get_state()->mip->read() & MIP_MSIP)==0,"IPI isolation");
    ipi=0;clint.store(4,4,reinterpret_cast<uint8_t*>(&ipi));
    check((f.p(1).get_state()->mip->read() & MIP_MSIP)==0,"IPI clear");
    uint64_t compare=10;
    clint.store(0x4008,8,reinterpret_cast<uint8_t*>(&compare));clint.tick(9);
    check((f.p(1).get_state()->mip->read()&MIP_MTIP)==0,"timer premature");clint.tick(1);
    check((f.p(1).get_state()->mip->read()&MIP_MTIP)!=0,"timer compare");
    if(iris) {
      auto* mmu0=p.get_mmu();auto* mmu1=f.p(1).get_mmu();
      mmu0->store<uint64_t>(0x80000000,7);
      check(mmu0->load_reserved<uint64_t>(0x80000000)==7,"LR value");
      mmu1->store<uint32_t>(0x80000004,9);
      check(!mmu0->store_conditional<uint64_t>(0x80000000,11),"peer overlapping store invalidates LR/SC");
      mmu0->load_reserved<uint64_t>(0x80000000);
      check(mmu0->store_conditional<uint64_t>(0x80000000,13),"uncontended SC");
      check(mmu1->amo<uint64_t>(0x80000000,[](auto old){return old+4;})==13,"AMO old value");
      check(mmu0->load<uint64_t>(0x80000000)==17,"shared AMO visibility");
      mmu0->store<uint64_t>(0x580000000ULL,42);
      bool scratch_amo=false,scratch_lr=false,scratch_sc=false;
      try { mmu0->amo<uint64_t>(0x580000000ULL,[](auto x){return x+1;}); } catch(const trap_t& t){scratch_amo=t.cause()==CAUSE_STORE_ACCESS;}
      try { mmu0->load_reserved<uint64_t>(0x580000000ULL); } catch(const trap_t& t){scratch_lr=t.cause()==CAUSE_LOAD_ACCESS;}
      try { mmu0->store_conditional<uint64_t>(0x580000000ULL,1); } catch(const trap_t& t){scratch_sc=t.cause()==CAUSE_STORE_ACCESS;}
      check(scratch_amo&&scratch_lr&&scratch_sc,"scratchpad rejects atomics but allows ordinary stores");
      check(mmu0->load<uint64_t>(0x580000000ULL)==42,"failed scratchpad AMO preserves contents");
      bool fault=false;try { mmu0->load<uint32_t>(0x90000000); }catch(const trap_t& t){fault=t.cause()==CAUSE_LOAD_ACCESS;}
      check(fault,"unmapped memory fault");
      // Discard is an RTL no-op. vm and discarded rd bits are not decode keys.
      exec(p,MATCH_VTDISCARD|(17<<7)|(1<<25));
      check(p.VU.mt_elt<uint32_t>(0,3,9)==309,"discard preserves tile state");
      p.get_state()->XPR.write(6,9);
      exec(p,MATCH_VTMV_V_T|(6<<15)|(12<<7));
      exec(p,(MATCH_VTMV_V_T|(6<<15)|(12<<7))^(1<<25));
      // A fresh tile read cannot silently obtain the upstream zero initialization.
      Fixture fresh(true);config(fresh.p(),32,1,4,4,1);
      fresh.p().get_state()->XPR.write(6,0);
      bool unknown=false;
      try { exec(fresh.p(),MATCH_VTMV_V_T|(6<<15)|(12<<7)); }
      catch(const std::runtime_error&) { unknown=true; }
      check(unknown,"uninitialized tile guard");
      illegal(p,(MATCH_VTMV_V_T^(1<<20))|(6<<15)|(12<<7));
      illegal(p,MATCH_MSETMTYPEI^(1<<20));
      // Column input exists; column output is missing in the elaborated OPU.
      config(p,32,1,32,32,1);
      for(unsigned col=0;col<32;col++) {
        for(unsigned row=0;row<32;row++)p.VU.elt<uint32_t>(8,row,true)=row*100+col;
        p.get_state()->XPR.write(6,(1<<24)|col);
        exec(p,MATCH_VTMV_T_V|(8<<20)|(6<<15));
      }
      p.get_state()->XPR.write(6,9);exec(p,MATCH_VTMV_V_T|(6<<15)|(12<<7));
      for(unsigned col=0;col<32;col++)check(p.VU.elt<uint32_t>(12,col)==900+col,"column-in row-out");
      p.get_state()->XPR.write(6,(1<<24)|9);
      bool unsupported_col=false;try{exec(p,MATCH_VTMV_V_T|(6<<15)|(12<<7));}catch(const std::runtime_error& error){unsupported_col=std::string(error.what()).find("IRIS_UNSUPPORTED_COLUMN_MOVE")!=std::string::npos;}
      check(unsupported_col,"unconfigured column output fails closed");
      p.get_state()->mstatus->write(p.get_state()->mstatus->read()|MSTATUS_FS);
      for(unsigned fmt=0;fmt<2;fmt++)for(unsigned base=0;base<256;base+=8) {
        p.VU.set_vl(5,6,8,0xc0|(fmt<<8));
        for(unsigned lane=0;lane<8;lane++) {
          const unsigned raw=base+lane;
          check(iris_fp8_to_f32(raw,fmt)==fp8_widen[fmt][raw],"all FP8 representations widen exactly");
          p.VU.elt<uint8_t>(8,lane,true)=raw;
          if(fmt) {softfloat_exceptionFlags=0;auto half=e5m2_to_f16(float8_t{uint8_t(raw)});check(half.v==(((raw&0x7c)==0x7c&&(raw&3))?0x7e00:raw<<8),"E5M2 to binary16 exact");}
        }
        p.get_state()->fflags->write(0);
        exec(p,MATCH_VFWCVTBF16_F_F_V|(1<<25)|(8<<20)|(16<<7));
        for(unsigned lane=0;lane<8;lane++)check(p.VU.elt<uint16_t>(16,lane)==uint16_t(fp8_widen[fmt][base+lane]>>16),"vector FP8 to BF16 all encodings");
        const unsigned expected=(fmt&&(base==120||base==248))?0x10:0;
        check(p.get_state()->fflags->read()==expected,"vector widening signaling NaN flag");
      }
      for(const auto& c:fp8_cases) {
        config(p,8,4,1,1,c.tk,c.fb);
        auto& cell=p.VU.mt_elt<uint32_t>(0,0,0);cell=c.acc;p.VU.iris_cell(cell,true);
        for(unsigned k=0;k<4;k++) {p.VU.elt<uint8_t>(8+2*k,0,true)=c.a[k];p.VU.elt<uint8_t>(16+2*k,0,true)=c.b[k];}
        p.get_state()->mstatus->write(p.get_state()->mstatus->read()|MSTATUS_FS);
        const unsigned seed_flags=(&c-fp8_cases)%3==0?0:(&c-fp8_cases)%3==1?4:0x1f;
        p.get_state()->frm->write(c.rm);p.get_state()->fflags->write(seed_flags);
        // OP-VE FP8 is not scalar FP-gated in the actual core.
        p.get_state()->mstatus->write(p.get_state()->mstatus->read()&~MSTATUS_FS);
        exec(p,(c.fa?MATCH_VTFMM_ALT_TVV:MATCH_VTFMM_TVV)|(8<<20)|(16<<15));
        if(cell!=c.want)throw std::runtime_error("FP8 integer oracle mismatch case="+std::to_string(&c-fp8_cases)+" got="+std::to_string(cell)+" want="+std::to_string(c.want));
        check(p.get_state()->fflags->read()==seed_flags,"OPU preserves fflags");
      }
      p.get_state()->mstatus->write(p.get_state()->mstatus->read()|MSTATUS_FS);
      // Both advertised scalar BF16 encodings are absent from the source
      // decoder. Exercise ordinary instruction stepping, including trap state.
      for(uint32_t absent:{uint32_t(MATCH_FCVT_BF16_S|(1<<15)|(2<<7)),
                           uint32_t(MATCH_FCVT_S_BF16|(1<<15)|(2<<7))}) {
        p.get_mmu()->store<uint32_t>(0x80000000,absent);
        p.get_mmu()->flush_icache();p.get_state()->pc=0x80000000;
        p.step(1);
        check(p.get_state()->mcause->read()==CAUSE_ILLEGAL_INSTRUCTION &&
              p.get_state()->mepc->read()==0x80000000 && p.get_state()->mtval->read()==absent,
              "source-absent scalar BF16 must deliver an architectural illegal trap");
      }
      struct DtypeGuard {uint32_t instruction,vtype;};
      for(auto unsupported:{DtypeGuard{MATCH_VFDIV_VV|(1<<25)|(8<<20)|(16<<15)|(24<<7),0xc0},DtypeGuard{MATCH_VFDIV_VV|(1<<25)|(8<<20)|(16<<15)|(24<<7),0x1c8}}) {
        p.VU.set_vl(5,6,1,unsupported.vtype);
        p.get_mmu()->store<uint32_t>(0x80000000,unsupported.instruction);
        p.get_mmu()->flush_icache();p.get_state()->pc=0x80000000;
        bool guarded=false;try{p.step(1);}catch(const std::runtime_error& error){guarded=std::string(error.what()).find("IRIS_UNSUPPORTED_DATATYPE")!=std::string::npos;}
        check(guarded,"unverified datatype behavior must fail closed at actual execution");
      }
      // FPComp ignores altfmt and interprets the e16 raw bits as H.
      p.VU.set_vl(5,6,1,0x1c8);p.get_state()->fflags->write(0);
      for(unsigned i=0;i<8;++i){p.VU.elt<uint16_t>(8,i,true)=0;p.VU.elt<uint16_t>(16,i,true)=0;}
      p.VU.elt<uint16_t>(8,0,true)=0x7e00;p.VU.elt<uint16_t>(16,0,true)=0x7e00;
      const uint32_t physical_h_compare=MATCH_VMFEQ_VV|(1<<25)|(8<<20)|(16<<15)|(24<<7);
      p.get_mmu()->store<uint32_t>(0x80000000,physical_h_compare);p.get_mmu()->flush_icache();p.get_state()->pc=0x80000000;p.step(1);
      check(p.get_state()->pc==0x80000004&&!p.VU.mask_elt(24,0)&&p.get_state()->fflags->read()==16,"actual stepping e16alt FPComp uses physical H and signaling compare flags");
      // The accelerator remains absent on hart 2 for both FP8 formats.
      illegal(f.p(2),MATCH_VTFMM_TVV);illegal(f.p(2),MATCH_VTFMM_ALT_TVV);

    }
    std::cout << "{\"functional_handlers\":\"pass\",\"mode\":\"" << (iris?"iris-experimental":"upstream-zvt") << "\",\"hart2_refusal\":true,\"arithmetic_sign_cases\":4,\"fp8_oracle_cases\":" << (iris?std::size(fp8_cases):0) << ",\"fp8_widen_representations\":" << (iris?512:0) << ",\"rtl_certified\":false}\n";
  } catch(trap_t& t) { std::cerr<<"unexpected trap "<<t.name()<<" cause="<<t.cause()<<" hart="<<last_hart<<" insn=0x"<<std::hex<<last_bits<<"\n";return 1; }
    catch(const std::exception& e) {std::cerr<<e.what()<<"\n";return 1;}
  return 0;
}
