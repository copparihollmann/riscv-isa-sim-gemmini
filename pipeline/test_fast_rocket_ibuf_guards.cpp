#include "fast_rocket_ibuf.hpp"
#include <iostream>
#include <stdexcept>
using Model=iris::frontend::FastRocketIBuf;
int main(){unsigned checks=0;auto refuses=[&](auto action){bool refused=false;try{action();}catch(const std::exception&){refused=true;}if(!refused)throw std::runtime_error("missing typed/knownness guard");++checks;};
 Model model;refuses([&]{model.commit();});
 Model::Inputs i;i.valid=true;i.ready=true;i.packet.known=0xffffffffu;i.packet.data=0x00010001u;refuses([&]{model.evaluate(i);});auto reset=i;reset.valid=false;reset.reset=true;model.evaluate(reset);model.commit();
 for(unsigned item=0;item<4;++item){auto bad=i;if(item==0)bad.packet.pc=1ull<<40;if(item==1)bad.packet.entry=32;if(item==2)bad.packet.history=256;if(item==3){bad.packet.pc=2;bad.packet.taken=true;bad.packet.branch_index=false;}refuses([&]{model.evaluate(bad);});refuses([&]{model.commit();});}
 auto bad=i;bad.packet.data=0x13;bad.packet.known=65535;refuses([&]{model.evaluate(bad);});
 bad=i;bad.packet.known=0;refuses([&]{model.evaluate(bad);});
 auto out=model.evaluate(i);if(!out.valid||!out.compressed)throw std::runtime_error("known source compressed flow");model.commit();++checks;
 // The retained compressed parcel is known although an unused adjacent input
 // parcel is unknown. The source rs3/raw upper payload remains unqualified.
 i.valid=false;i.ready=false;i.packet.data=0;i.packet.known=0;out=model.evaluate(i);if(!out.valid||!out.compressed||!out.instruction_known||out.raw_known!=65535||out.rs3_known)throw std::runtime_error("inactive adjacent payload laundered");model.commit();++checks;
 i.kill=true;model.evaluate(i);model.commit();i.kill=false;out=model.evaluate(i);if(out.valid)throw std::runtime_error("kill retained buffered instruction");model.commit();++checks;refuses([&]{model.commit();});
 std::cout<<"PASS "<<checks<<" width/knownness/kill/phase checks\n";
}
