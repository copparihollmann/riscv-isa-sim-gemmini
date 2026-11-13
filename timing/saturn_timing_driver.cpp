#include "saturn_timing.hpp"
#include <charconv>
#include <iostream>
#include <sstream>
#include <stdexcept>
using namespace iris::saturn;
static std::uint64_t number(std::istringstream&s){std::string t;if(!(s>>t))throw std::invalid_argument("Incomplete physical Saturn boundary");std::uint64_t v=0;auto r=std::from_chars(t.data(),t.data()+t.size(),v);if(r.ec!=std::errc{}||r.ptr!=t.data()+t.size())throw std::invalid_argument("Unsigned physical integer required");return v;}
static void emit(std::uint64_t edge,const ReferenceOutputs&o){std::cout<<"SATURN_FRAME "<<edge;for(auto v:o.words)std::cout<<' '<<v;std::cout<<'\n';}
int main(int argc,char**argv){try{
 if(argc!=8||std::string(argv[1])!="--reference-two-state"||std::string(argv[2])!="--profile"||std::string(argv[4])!="--hart"||std::string(argv[6])!="--seed")throw std::invalid_argument("Explicit --reference-two-state --profile compute|rocket --hart N --seed N required");Profile p=std::string(argv[3])=="compute"?Profile::Compute128:std::string(argv[3])=="rocket"?Profile::Rocket256:throw std::invalid_argument("Unknown configured runtime profile");std::istringstream hs(argv[5]),ss(argv[7]);auto hart=number(hs),seed=number(ss);if(seed>0xffffffffULL||hart>2)throw std::invalid_argument("Hart/seed exceeds source profile");SaturnTimingCut m(p,hart,seed,ReferenceScope::ExplicitTwoStateWithExternalDefinedness);std::uint64_t edge=0;
 for(std::string line;std::getline(std::cin,line);){std::istringstream s(line);std::string op;if(!(s>>op))continue;if(op=="sample"){emit(edge,m.sample());continue;}if(op=="commit"){m.commit();continue;}if(op!="step"&&op!="evaluate"&&op!="repeat")throw std::invalid_argument("Unsupported Saturn reference protocol operation");edge=number(s);ReferenceInputs i;i.words.resize(SaturnTimingCut::input_fields(p).size());for(auto&v:i.words)v=number(s);std::string extra;if(s>>extra)throw std::invalid_argument("Extra physical Saturn fields");if(op=="step")emit(edge,m.step(i));else{m.evaluate(i);if(op=="repeat"){auto before=m.sample();for(unsigned n=0;n<3;n++){m.evaluate(i);if(m.sample().words!=before.words)throw std::runtime_error("Same-input settle changed two-state reference output");}emit(edge,before);m.commit();}}}
 std::cerr<<"SATURN_REFERENCE_EDGES "<<m.edges()<<'\n';return 0;
}catch(const std::exception&e){std::cerr<<"Saturn reference refused: "<<e.what()<<'\n';return 2;}}
