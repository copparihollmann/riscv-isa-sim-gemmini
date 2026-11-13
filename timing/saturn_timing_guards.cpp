#include "saturn_timing.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
using namespace iris::saturn;
int main(int argc,char**argv){try{
 if(argc!=3)throw std::invalid_argument("profile input");
 const Profile p=std::string(argv[1])=="compute"?Profile::Compute128:Profile::Rocket256;
 SaturnTimingCut m(p,p==Profile::Compute128?0:2,17,ReferenceScope::ExplicitTwoStateWithExternalDefinedness);
 unsigned refusals=0,settles=0,modified=0; auto reject=[&](auto f){try{f();}catch(const std::exception&){++refusals;return;}throw std::runtime_error("Missing phase rejection");};
 reject([&]{m.sample();});reject([&]{m.commit();});
 std::ifstream in(argv[2]);std::string op;unsigned edge;const auto fields=SaturnTimingCut::input_fields(p);unsigned ready=0,reset=0;
 for(unsigned n=0;n<fields.size();++n){if(fields[n].name=="auto_atl_out_a_ready")ready=n;if(fields[n].name=="reset")reset=n;}
 while(in>>op>>edge){
  ReferenceInputs i;for(unsigned n=0;n<fields.size();++n){std::uint64_t w;if(!(in>>w))throw std::runtime_error("Truncated frame");i.words.push_back(w);}
  if(op!="step"||edge!=m.edges())throw std::runtime_error("Not continuous");
  m.evaluate(i);const auto expected=m.sample().words;
  for(unsigned n=0;n<3;++n){m.evaluate(i);if(m.sample().words!=expected)throw std::runtime_error("Same-edge repeated settle differs");++settles;}
  auto changed=i;changed.words[ready]^=1;m.evaluate(changed);m.sample();m.evaluate(i);
  if(m.sample().words!=expected)throw std::runtime_error("Revised same-edge ready advanced state");++modified;
  if(edge%257==0){auto bad=i;bad.words[reset]=2;reject([&]{m.evaluate(bad);});reject([&]{m.sample();});reject([&]{m.commit();});m.evaluate(i);if(m.sample().words!=expected)throw std::runtime_error("Guard recovery changed state");}
  m.commit();reject([&]{m.sample();});reject([&]{m.commit();});
 }
 std::cerr<<"SATURN_GUARDS {\"edges\":"<<m.edges()<<",\"repeated_same_edge_settles\":"<<settles<<",\"revised_ready_restores\":"<<modified<<",\"refusals\":"<<refusals<<"}\n";
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 2;}}
