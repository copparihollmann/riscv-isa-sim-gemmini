#include "shuttle_memory_system.hpp"
#include "shuttle_memory_system_paths.hpp"
#include "verilated.h"
#include <iostream>
#include <stdexcept>
namespace S=iris::shuttle_system;
namespace P=iris::shuttle_memory;
unsigned checks=0;
void need(bool x,const char*m){++checks;if(!x)throw std::runtime_error(m);}
S::Bits known(unsigned w){S::Bits b;for(unsigned i=0;i<w;++i)b.limbs[i/64]|=1ULL<<(i%64);return b;}
template<class F>void rejects(F f){bool caught=false;try{f();}catch(const std::exception&){caught=true;}need(caught,"malformed operation admitted");}
int main(){try{
  VerilatedContext foreign;Verilated::threadContextp(&foreign);
  S::System model(1,{"shuttle-guards"},iris::serial_memory::AssertionPolicy::SuppressOnlyWhileBothExternalResets);
  need(Verilated::threadContextp()==&foreign,"System constructor context");
  auto fields=model.input_fields();std::vector<S::Input>in(fields.size());
  for(unsigned i=0;i<in.size();++i){in[i].known=known(fields[i].width);if(fields[i].name.ends_with("_reset")||fields[i].name.ends_with("/reset")||fields[i].name.ends_with("/iris_pad_reset_io"))in[i].value=S::Bits(1);}
  rejects([&]{model.sample();});rejects([&]{model.commit({true,true,true,true});});
  for(unsigned i=0;i<in.size();++i){auto bad=in;bad[i].known.limbs[0]&=~1ULL;rejects([&]{model.evaluate(bad);});rejects([&]{model.sample();});rejects([&]{model.commit({true,true,true,true});});
    if(fields[i].width<256){bad=in;bad[i].value.limbs[fields[i].width/64]|=1ULL<<(fields[i].width%64);rejects([&]{model.evaluate(bad);});bad=in;bad[i].known.limbs[fields[i].width/64]|=1ULL<<(fields[i].width%64);rejects([&]{model.evaluate(bad);});}
    need(Verilated::threadContextp()==&foreign,"failed System input context leak");
  }
  rejects([&]{model.external_input_index("shuttle1_tile","auto_hartid_in");});
  rejects([&]{model.external_input_index("shuttle0_cache","auto_out_a_ready");});
  rejects([&]{model.external_input_index("system","fabric/DigitalTop/_tile_prci_domain_auto_tl_master_clock_xing_out_a_valid");});
  unsigned path_edges=0;
  for(auto kind:{P::Path::Tile,P::Path::PRCI,P::Path::Uncore}){
    P::Paths path(kind,31);need(Verilated::threadContextp()==&foreign,"Paths constructor context");std::vector<P::Bits>pins(path.input_fields().size());
    rejects([&]{path.evaluate(pins);});rejects([&]{path.sample();});rejects([&]{path.commit();});need(path.edges()==0,"failed Paths phase advanced edge");
    for(unsigned i=0;i<pins.size();++i)if(path.input_fields()[i].name=="reset"||path.input_fields()[i].name.ends_with("_reset"))pins[i]=P::Bits(1);
    path.evaluate(pins);auto first=path.sample();path.evaluate(pins);need(path.sample()==first,"Paths same-edge evaluation changed output");need(path.edges()==0,"Paths evaluation advanced clock");path.commit();need(path.edges()==1,"Paths committed edge count");++path_edges;rejects([&]{path.sample();});rejects([&]{path.commit();});need(Verilated::threadContextp()==&foreign,"Paths phase/error context leak");
  }
  std::cout<<"{\"status\":\"passed\",\"checks\":"<<checks<<",\"unknown_field_controls\":"<<in.size()<<",\"source_path_reset_edges\":"<<path_edges<<",\"system_RTL_edges\":0}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
