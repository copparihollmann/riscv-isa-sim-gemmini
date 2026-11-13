#include "scalar_memory.hpp"
#include <iostream>
#include <stdexcept>

using namespace iris;
static unsigned checks=0;
static void check(bool value, const char* message) {
  ++checks;if (!value) throw std::runtime_error(message);
}
int main() {
  std::array<uint64_t,32> regs{};
  for (unsigned i=0;i<32;++i) regs[i]=0x80000000+i*256;
  regs[0]=UINT64_MAX; // x0 must still be zero.
  for (unsigned rs=0;rs<32;++rs) for (unsigned f3=0;f3<7;++f3) {
    const uint32_t raw=(0xffcu<<20)|(rs<<15)|(f3<<12)|0x03;
    const auto a=scalar_memory_access(raw,regs);
    check(a.decode==MemoryDecode::scalar && a.kind==AccessKind::load &&
          a.bytes==(1u<<(f3&3)) && a.address==(rs?regs[rs]:0)-4,"signed load EA/width");
  }
  for (unsigned width=0;width<4;++width) {
    const uint32_t raw=(0x7fu<<25)|(5u<<15)|(width<<12)|(0x1cu<<7)|0x23;
    const auto a=scalar_memory_access(raw,regs);
    check(a.decode==MemoryDecode::scalar && a.kind==AccessKind::store &&
          a.bytes==(1u<<width) && a.address==regs[5]-4,"signed store EA/width");
  }
  for (unsigned op:{0x07u,0x27u}) for (unsigned width=0;width<8;++width) {
    const auto a=scalar_memory_access((7u<<15)|(width<<12)|op,regs);
    if (width==0 || width>=5) check(a.decode==MemoryDecode::vector,"RVV cannot masquerade as scalar FP");
    else if (width<=3) check(a.decode==MemoryDecode::scalar && a.bytes==(1u<<width),"scalar FP width");
    else check(a.decode==MemoryDecode::unresolved,"reserved FP width is unresolved");
  }
  for (unsigned fn:{0u,1u,2u,3u,4u,8u,12u,16u,20u,24u,28u}) for (unsigned width:{2u,3u}) {
    const auto a=scalar_memory_access((fn<<27)|(3u<<15)|(width<<12)|0x2f,regs);
    check(a.decode==MemoryDecode::scalar && a.bytes==(1u<<width) && a.address==regs[3] &&
          a.kind==(fn==2?AccessKind::lr:fn==3?AccessKind::sc:AccessKind::amo),"atomic EA/kind");
  }
  // Exhaust every compressed immediate encoding for each RV64 C memory form.
  for (unsigned q:{0u,2u}) for (unsigned f3:{1u,2u,3u,5u,6u,7u})
    for (unsigned bits=0;bits<2048;++bits) {
      const uint32_t raw=(f3<<13)|(bits<<2)|q;
      const auto a=scalar_memory_access(raw,regs);
      const bool store=f3>=5;const unsigned width=(f3==2||f3==6)?4:8;
      // Independent bit-position oracle from the C immediate tables.
      auto bit=[&](unsigned n){ return uint64_t((raw>>n)&1); };
      uint64_t offset=0,base=0;
      if (q==0) {
        base=regs[8+((raw>>7)&7)];
        if (width==4) offset=bit(6)*4+bit(10)*8+bit(11)*16+bit(12)*32+bit(5)*64;
        else offset=bit(10)*8+bit(11)*16+bit(12)*32+bit(5)*64+bit(6)*128;
      } else {
        base=regs[2];
        if (store && width==4) offset=bit(9)*4+bit(10)*8+bit(11)*16+bit(12)*32+bit(7)*64+bit(8)*128;
        if (store && width==8) offset=bit(10)*8+bit(11)*16+bit(12)*32+bit(7)*64+bit(8)*128+bit(9)*256;
        if (!store && width==4) offset=bit(4)*4+bit(5)*8+bit(6)*16+bit(12)*32+bit(2)*64+bit(3)*128;
        if (!store && width==8) offset=bit(5)*8+bit(6)*16+bit(12)*32+bit(2)*64+bit(3)*128+bit(4)*256;
      }
      check(a.decode==MemoryDecode::scalar && a.bytes==width && a.address==base+offset &&
            a.kind==(store?AccessKind::store:AccessKind::load),"compressed EA mismatch");
    }
  check(scalar_memory_access(0x13,regs).decode==MemoryDecode::none,"ALU classified as memory");

  std::map<std::string,std::vector<RoutedStage>> paths{
    {"tcm0",{{{"sram","bank0",3,1,0,32,1,"synthetic"},true}}},
    {"tcm1",{{{"sram","bank1",3,1,0,32,1,"synthetic"},true}}},
    {"dram",{{{"serial","serial",5,1,64,8,2,"synthetic"},false}}}};
  std::vector<AddressRoute> regions;
  for (unsigned h=0;h<3;++h) {
    regions.push_back({h,0x70000000,0x20000,64,0,"tcm0"});
    regions.push_back({h,0x70000000,0x20000,64,64,"tcm1"});
    regions.push_back({h,0x80000000,0x100000000,0,0,"dram"});
  }
  ScalarMemoryRoutes routes(3,regions,paths);
  Machine clock(3,100);MemoryPaths fabric(clock,{{"bank0",1,"synthetic"},{"bank1",1,"synthetic"},{"serial",1,"synthetic"}});
  unsigned visible=0;
  for (unsigned h=0;h<3;++h) {
    ScalarAccess access{MemoryDecode::scalar,AccessKind::load,0x80000000,8};
    fabric.submit(routes.request(h,access,0x1000,1,{},[&]{++visible;}));
  }
  clock.run_until(18);check(visible==0,"functional effect happened before routed response");
  clock.run_until(19);check(visible==1,"routed response completion missing");
  clock.drain();check(visible==3 && clock.now()==51,"three-hart routed serial contention lost");
  auto a=fabric.submit(routes.request(0,{MemoryDecode::scalar,AccessKind::store,0x70000000,8},0,1,{},{}));
  auto b=fabric.submit(routes.request(1,{MemoryDecode::scalar,AccessKind::load,0x70000040,8},0,1,{},{}));
  clock.drain();check(clock.nodes()[a.nodes[0]].start==clock.nodes()[b.nodes[0]].start,"independent banks serialized");
  for (uint64_t address:{uint64_t{0x70020000},UINT64_MAX,uint64_t{0x7000003f}}) {
    bool refused=false;
    try { routes.request(2,{MemoryDecode::scalar,AccessKind::load,address,8},0,1,{},{}); }
    catch (const std::exception&) {refused=true;}
    check(refused,"unmapped/wrapping/cross-bank request silently accepted");
  }
  regions.push_back(regions[0]);ScalarMemoryRoutes ambiguous(3,regions,paths);
  bool refused=false;
  try { ambiguous.request(0,{MemoryDecode::scalar,AccessKind::load,0x70000000,8},0,1,{},{}); }
  catch(const std::runtime_error&) {refused=true;}
  check(refused,"ambiguous route used arbitrary precedence");
  std::cout<<"scalar memory checks="<<checks<<" passed; synthetic parameters only\n";
}
