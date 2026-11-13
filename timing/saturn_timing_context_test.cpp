#include "saturn_timing.hpp"
#include "verilated.h"
#include <algorithm>
#include <array>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
using namespace iris::saturn;
struct Frame {ReferenceInputs input;std::vector<std::uint64_t> gold,mask;};
static std::vector<Frame> load(Profile p,const char*ip,const char*op,const char*mp){
 std::ifstream ins(ip),outs(op),masks(mp,std::ios::binary);std::string line;std::vector<Frame> rows;char magic[8];std::uint64_t count,words;masks.read(magic,8);masks.read(reinterpret_cast<char*>(&count),8);masks.read(reinterpret_cast<char*>(&words),8);if(std::string(magic,8)!="SATMSK01"||words!=SaturnTimingCut::output_fields(p).size())throw std::invalid_argument("Mask header");
 while(std::getline(ins,line)){Frame row;std::istringstream fields(line);std::string tag;std::uint64_t edge,w;fields>>tag>>edge;if(tag!="step"||edge!=rows.size())throw std::invalid_argument("Input continuity");while(fields>>w)row.input.words.push_back(w);do{if(!std::getline(outs,line))throw std::invalid_argument("Missing output");}while(line.rfind("SATURN_FRAME ",0));std::istringstream values(line);values>>tag>>w;if(w!=edge)throw std::invalid_argument("Output continuity");while(values>>w)row.gold.push_back(w);if(row.input.words.size()!=SaturnTimingCut::input_fields(p).size()||row.gold.size()!=words)throw std::invalid_argument("Incomplete frame");row.mask.resize(words);masks.read(reinterpret_cast<char*>(row.mask.data()),8*words);if(!masks)throw std::invalid_argument("Truncated masks");rows.push_back(std::move(row));}
 if(rows.size()!=count)throw std::invalid_argument("Mask count");return rows;
}
int main(int argc,char**argv){try{
 if(argc!=11)throw std::invalid_argument("mode +three(input output mask)");const unsigned mode=std::stoul(argv[1]);std::array<std::vector<Frame>,3> traces;for(unsigned h=0;h<3;++h)traces[h]=load(h==2?Profile::Rocket256:Profile::Compute128,argv[2+3*h],argv[3+3*h],argv[4+3*h]);
 VerilatedContext foreign0,foreign1;const char*a0[]={"foreign0","+iris-owner=foreign0"};const char*a1[]={"foreign1","+iris-owner=foreign1"};foreign0.commandArgs(2,a0);foreign1.commandArgs(2,a1);foreign0.randSeed(32001);foreign1.randSeed(32002);foreign0.randReset(0);foreign1.randReset(2);std::array<std::unique_ptr<SaturnTimingCut>,3> cores;std::array<unsigned,3> order=mode%2?std::array<unsigned,3>{2,1,0}:std::array<unsigned,3>{0,1,2};std::uint64_t context_checks=0,field_checks=0,settles=0,edges=0,invalids=0;
 auto chosen=[&](unsigned h,std::uint64_t edge){auto*ctx=(h+edge)%2?&foreign0:&foreign1;Verilated::threadContextp(ctx);return ctx;};auto preserved=[&](VerilatedContext*ctx,const char*where){if(Verilated::threadContextp()!=ctx)throw std::runtime_error(std::string(where)+" changed caller context");++context_checks;};
 for(auto h:order){auto*prior=chosen(h,0);
#ifdef IRIS_CONTEXT_API
  const std::string own="+iris-owner=hart"+std::to_string(h);const std::array<std::string_view,1> args{own};cores[h]=std::make_unique<SaturnTimingCut>(h==2?Profile::Rocket256:Profile::Compute128,h,17+h*37,ReferenceScope::ExplicitTwoStateWithExternalDefinedness,args);
#else
  cores[h]=std::make_unique<SaturnTimingCut>(h==2?Profile::Rocket256:Profile::Compute128,h,17+h*37,ReferenceScope::ExplicitTwoStateWithExternalDefinedness);
#endif
  preserved(prior,"Construction");
 }
 const auto n=std::max({traces[0].size(),traces[1].size(),traces[2].size()});
 for(std::uint64_t e=0;e<n;++e){if(mode==2)order=e%2?std::array<unsigned,3>{1,0,2}:std::array<unsigned,3>{2,1,0};
  for(auto h:order)if(e<traces[h].size()){
   auto*prior=chosen(h,e);auto&m=*cores[h];const auto&f=traces[h][e];m.evaluate(f.input);preserved(prior,"Evaluate");
#ifdef IRIS_CONTEXT_API
   if(e%257==0){const auto arg=m.context_argument("iris-owner=");if(arg!="+iris-owner=hart"+std::to_string(h))throw std::runtime_error("Own-context plusarg not selected");preserved(prior,"Plusarg query");}
#endif
   const auto actual=m.sample().words;preserved(prior,"Sample");for(unsigned word=0;word<actual.size();++word)if(f.mask[word]){if((actual[word]^f.gold[word])&f.mask[word])throw std::runtime_error("Qualified interleaved output differs hart="+std::to_string(h)+" edge="+std::to_string(e)+" word="+std::to_string(word));++field_checks;}
   if(e%257==0){m.evaluate(f.input);preserved(prior,"Repeated evaluate");if(m.sample().words!=actual)throw std::runtime_error("Repeated same-edge frame changed");preserved(prior,"Repeated sample");++settles;auto bad=f.input;bad.words[0]=2;bool rejected=false;try{m.evaluate(bad);}catch(const std::invalid_argument&){rejected=true;}if(!rejected)throw std::runtime_error("Width error accepted");preserved(prior,"Failed evaluate");bool stale=false;try{m.commit();}catch(const std::logic_error&){stale=true;}if(!stale)throw std::runtime_error("Stale commit accepted");preserved(prior,"Failed commit");m.evaluate(f.input);preserved(prior,"Recovered evaluate");++invalids;}
  }
  for(unsigned at=0;at<3;++at){const auto h=order[2-at];if(e<traces[h].size()){auto*prior=chosen(h,e+1);cores[h]->commit();preserved(prior,"Commit");++edges;}}
 }
 for(auto h:order){auto*prior=chosen(h,1);cores[h].reset();preserved(prior,"Destruction");}
 std::cerr<<"SATURN_CONTEXT_RESULT {\"mode\":"<<mode<<",\"source_core_edges\":"<<edges<<",\"qualified_field_checks\":"<<field_checks<<",\"caller_context_checks\":"<<context_checks<<",\"same_edge_repeats\":"<<settles<<",\"recoverable_invalid_frames\":"<<invalids<<"}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
