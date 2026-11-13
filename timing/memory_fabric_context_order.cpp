#include "noc_network.hpp"
#include "verilated.h"
#include <algorithm>
#include <array>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <vector>
using namespace iris::noc;
struct Row{std::uint64_t tb;NetworkInputs in;};
static std::uint64_t comparisons=0,restorations=0;
static void restored(VerilatedContext*expected){if(Verilated::threadContextp()!=expected)throw std::runtime_error("caller context not restored");++restorations;}
int main(int argc,char**argv){try{
 if(argc!=2)throw std::invalid_argument("actual reset physical input file required");std::ifstream file(argv[1]);if(!file)throw std::runtime_error("input unavailable");std::vector<Row>rows;for(std::string line;std::getline(file,line);){std::istringstream s(line);std::string op;s>>op;if(op.empty())continue;if(op!="step")throw std::runtime_error("step only");Row r{};if(!(s>>r.tb))throw std::runtime_error("time missing");for(auto&v:r.in.values)if(!(s>>v))throw std::runtime_error("pin missing");std::string extra;if(s>>extra)throw std::runtime_error("extra pin");rows.push_back(r);}
 if(rows.size()<1000)throw std::runtime_error("substantial actual reset trace required");auto inf=IrisNoCNetwork::input_fields();unsigned reset=inf.size();for(unsigned i=0;i<inf.size();++i)if(inf[i].name.ends_with("_reset"))reset=i;if(reset==inf.size()||rows.front().in.values[reset]!=1)throw std::runtime_error("actual reset missing");
 auto fields=IrisNoCNetwork::output_fields();std::vector<int>valid(fields.size(),-1);for(unsigned i=0;i<fields.size();++i){auto pos=fields[i].name.find("_bits_");if(pos==std::string_view::npos)continue;auto name=std::string(fields[i].name.substr(0,pos))+"_valid";for(unsigned j=0;j<fields.size();++j)if(fields[j].name==name)valid[i]=j;if(valid[i]<0)throw std::runtime_error("unclassified payload");}
 std::array<unsigned,3>seeds={1,17,113};std::array<std::vector<NetworkOutputs>,3>golden;for(unsigned j=0;j<3;++j){IrisNoCNetwork model(seeds[j]);for(auto&r:rows)golden[j].push_back(model.step(r.in));}
 VerilatedContext foreign;foreign.randReset(2);foreign.randSeed(991); // no commandArgs: old wrapper's wrong-context plusargs use fails.
 const std::array<std::array<unsigned,3>,3>orders={{{0,1,2},{2,0,1},{2,1,0}}};
 for(unsigned scenario=0;scenario<orders.size();++scenario){std::array<std::unique_ptr<IrisNoCNetwork>,3>models;for(auto j:orders[scenario]){Verilated::threadContextp(&foreign);models[j]=std::make_unique<IrisNoCNetwork>(seeds[j]);restored(&foreign);}
  for(unsigned edge=0;edge<rows.size();++edge){for(unsigned k=0;k<3;++k){auto j=orders[(scenario+edge)%3][k];auto&m=*models[j];Verilated::threadContextp(&foreign);m.evaluate(rows[edge].in);restored(&foreign);Verilated::threadContextp(&foreign);auto actual=m.sample();restored(&foreign);
    if(!rows[edge].in.values[reset])for(unsigned field=0;field<fields.size();++field)if(valid[field]<0||golden[j][edge].values[valid[field]]){++comparisons;if(actual.values[field]!=golden[j][edge].values[field])throw std::runtime_error("owner-context order mismatch scenario="+std::to_string(scenario)+" seed="+std::to_string(seeds[j])+" TB="+std::to_string(rows[edge].tb)+" field="+std::string(fields[field].name));}
    Verilated::threadContextp(&foreign);m.commit();restored(&foreign);
   }}
  for(auto&m:models){if(m->edges()!=rows.size())throw std::runtime_error("wrong edge count");Verilated::threadContextp(&foreign);m.reset();restored(&foreign);}
 }
 std::cout<<"{\"status\":\"passed\",\"rows_per_peer\":"<<rows.size()<<",\"peers\":3,\"construction_orders\":3,\"interleaving_orders\":3,\"physical_word_comparisons\":"<<comparisons<<",\"caller_context_restoration_checks\":"<<restorations<<",\"every_entry_with_foreign_context\":true,\"unreset_history_order_independence_certified\":false}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
