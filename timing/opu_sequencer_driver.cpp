#include "opu_sequencer.hpp"
#include <charconv>
#include <iostream>
#include <sstream>
#include <stdexcept>
using namespace iris::opu;
static std::uint64_t number(std::istringstream& s){std::string t;if(!(s>>t))throw std::invalid_argument("Incomplete physical OPU boundary");std::uint64_t v=0;auto r=std::from_chars(t.data(),t.data()+t.size(),v);if(r.ec!=std::errc{}||r.ptr!=t.data()+t.size())throw std::invalid_argument("Unsigned physical integer required");return v;}
static void emit(std::uint64_t edge,const SequencerOutputs& o){std::cout<<edge;for(unsigned k=0;k<o.values.size();k++){std::cout<<' ';if(o.defined[k])std::cout<<o.values[k];else std::cout<<'x';}std::cout<<'\n';}
int main(int argc,char**argv){try{
 if(argc!=3||std::string(argv[1])!="--seed")throw std::invalid_argument("Explicit --seed N required");std::istringstream st(argv[2]);auto seed=number(st);if(seed>0xffffffffULL)throw std::invalid_argument("Seed exceeds 32 bits");IrisOPUSequencer m(seed);std::uint64_t edge=0;
 for(std::string line;std::getline(std::cin,line);){std::istringstream s(line);std::string op;if(!(s>>op))continue;
  if(op=="sample"){emit(edge,m.sample());continue;}if(op=="commit"){m.commit();continue;}
  if(op!="step"&&op!="evaluate"&&op!="repeat")throw std::invalid_argument("Unsupported OPU protocol operation");edge=number(s);SequencerInputs i{};for(auto&v:i.values)v=number(s);std::string extra;if(s>>extra)throw std::invalid_argument("Extra physical OPU fields");
  if(op=="step")emit(edge,m.step(i));else {m.evaluate(i);if(op=="repeat"){auto before=m.sample();for(unsigned n=0;n<7;n++){m.evaluate(i);auto after=m.sample();for(unsigned k=0;k<before.values.size();k++)if(before.defined[k]!=after.defined[k]||(before.defined[k]&&before.values[k]!=after.values[k]))throw std::runtime_error("Repeated settle changed defined output");}emit(edge,before);m.commit();}}
 }std::cerr<<"IRIS_OPU_EDGES "<<m.edges()<<'\n';return 0;
}catch(const std::exception&e){std::cerr<<"OPU sequencer refused: "<<e.what()<<'\n';return 2;}}
