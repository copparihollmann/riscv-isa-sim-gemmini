#include "noc_network.hpp"
#include <charconv>
#include <iostream>
#include <sstream>
#include <stdexcept>
using namespace iris::noc;
static std::uint64_t number(std::istringstream& s){std::string t;if(!(s>>t))throw std::invalid_argument("Incomplete physical TL boundary");std::uint64_t v=0;auto r=std::from_chars(t.data(),t.data()+t.size(),v);if(r.ec!=std::errc{}||r.ptr!=t.data()+t.size())throw std::invalid_argument("Unsigned physical integer required");return v;}
static void emit(std::uint64_t tb,const NetworkOutputs& o){std::cout<<tb;for(auto x:o.values)std::cout<<' '<<x;std::cout<<'\n';}
int main(int argc,char** argv){try{
 if(argc!=3||std::string(argv[1])!="--seed")throw std::invalid_argument("Explicit --seed N required");std::istringstream seed_text(argv[2]);auto seed=number(seed_text);if(seed>0xffffffffULL)throw std::invalid_argument("Seed exceeds32bits");IrisNoCNetwork network(seed);std::uint64_t last_tb=0;
 for(std::string line;std::getline(std::cin,line);){std::istringstream s(line);std::string op;if(!(s>>op))continue;
  if(op=="save"||op=="restore"){std::string path;if(!(s>>path))throw std::invalid_argument("Snapshot path required");if(op=="save")network.save(path);else network.restore(path);continue;}
  if(op=="sample"){emit(last_tb,network.sample());continue;}if(op=="commit"){network.commit();continue;}
  if(op!="step"&&op!="evaluate"&&op!="repeat"){throw std::invalid_argument("Unsupported NoC protocol operation");}
  auto tb=number(s);NetworkInputs i{};for(auto& x:i.values)x=number(s);std::string extra;if(s>>extra)throw std::invalid_argument("Extra physical TL fields");last_tb=tb;
  if(op=="step")emit(tb,network.step(i));else{network.evaluate(i);if(op=="repeat"){auto before=network.sample();for(unsigned n=0;n<7;n++){network.evaluate(i);if(network.sample().values!=before.values)throw std::runtime_error("Repeated evaluation changed settled outputs");}emit(tb,before);network.commit();}}
 }
 std::cerr<<"IRIS_NETWORK_EDGES "<<network.edges()<<'\n';return 0;
}catch(const std::exception& e){std::cerr<<"NoC network refused: "<<e.what()<<'\n';return 2;}}
