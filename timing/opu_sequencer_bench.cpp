#include "opu_sequencer.hpp"
#include <chrono>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <sstream>
#include <vector>
using namespace iris::opu;
static unsigned input_index(std::string_view s){auto fs=IrisOPUSequencer::input_fields();for(unsigned j=0;j<fs.size();j++)if(fs[j].name==s)return j;throw std::runtime_error("Missing physical input");}
static bool equal(const SequencerOutputs&a,const SequencerOutputs&b){for(unsigned k=0;k<a.values.size();k++)if(a.defined[k]!=b.defined[k]||(a.defined[k]&&a.values[k]!=b.values[k]))return false;return true;}
int main(int argc,char**argv){try{
 if(argc!=2)throw std::invalid_argument("Boundary input file required");std::ifstream file(argv[1]);if(!file)throw std::runtime_error("Input unavailable");std::vector<SequencerInputs> rows;
 for(std::string line;std::getline(file,line);){std::istringstream s(line);std::string op;std::uint64_t edge;s>>op>>edge;if(op!="step"||edge!=rows.size())throw std::runtime_error("Expected consecutive step edges");SequencerInputs i;for(auto&v:i.values)if(!(s>>v))throw std::runtime_error("Incomplete boundary");rows.push_back(i);}
 unsigned refusals=0;auto refused=[&](auto fn){try{fn();}catch(const std::exception&){++refusals;return;}throw std::runtime_error("Unsafe SDK operation accepted");};IrisOPUSequencer guard(0);refused([&]{guard.sample();});refused([&]{guard.commit();});guard.step(rows.at(0));refused([&]{guard.sample();});refused([&]{guard.commit();});auto valid=rows.at(1);guard.evaluate(valid);auto bad=valid;bad.values[input_index("reset")]=2;refused([&]{guard.evaluate(bad);});refused([&]{guard.commit();});refused([&]{guard.sample();});if(guard.edges()!=1)throw std::runtime_error("Bad evaluation changed edge count");guard.step(valid);
 auto invalid_op=rows.at(3);invalid_op.values[input_index("io_dis_bits_bits")]=0;guard.evaluate(rows.at(2));refused([&]{guard.evaluate(invalid_op);});refused([&]{guard.commit();});if(guard.edges()!=2)throw std::runtime_error("Rejected instruction changed state");
 std::cout<<"{\"source_identity\":\""<<IrisOPUSequencer::source_identity()<<"\",\"lifecycle_refusals\":"<<refusals<<",\"edges_per_repetition\":"<<rows.size()<<",\"runs\":[";
 std::uint64_t reference=0;
 for(unsigned rep=0;rep<7;rep++){
  IrisOPUSequencer model(rep);std::vector<SequencerOutputs> results(rows.size());auto start=std::chrono::steady_clock::now();
  for(unsigned e=0;e<rows.size();e++)results[e]=model.step(rows[e]);
  double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();std::uint64_t mix=1469598103934665603ULL,defined=0;
  for(const auto&o:results)for(unsigned k=0;k<o.values.size();k++)if(o.defined[k]){mix^=o.values[k];mix*=1099511628211ULL;++defined;}
  if(rep&&mix!=reference)throw std::runtime_error("Unknown reset leaked into defined benchmark");reference=mix;
  if(rep)std::cout<<',';std::cout<<"{\"seed\":"<<rep<<",\"host_seconds\":"<<seconds<<",\"edges_per_second\":"<<rows.size()/seconds<<",\"defined_field_mix\":"<<mix<<",\"defined_words\":"<<defined<<'}';
 }
 // Real ready/hazard changes are allowed during same-edge convergence. Restore
 // the physical inputs and compare with the original settled result before
 // committing exactly one edge. No output/state is used as an input.
 IrisOPUSequencer phase(0);std::uint64_t settle_checks=0;
 for(auto i:rows){phase.evaluate(i);auto before=phase.sample();auto changed=i;for(auto n:{"io_rvs1_ready","io_rvs2_ready","io_pipe_write_req_available"})changed.values[input_index(n)]^=1;changed.values[input_index("io_older_writes")]^=~0ULL;phase.evaluate(changed);phase.sample();phase.evaluate(i);if(!equal(before,phase.sample()))throw std::runtime_error("Same-edge ready/hazard restoration changed controller state");phase.commit();++settle_checks;}
 std::cout<<"],\"ready_hazard_settle_edges\":"<<settle_checks<<",\"idle_skips\":0,\"hardware_contacted\":false}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
