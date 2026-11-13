#include "noc_full_router.hpp"
#include <charconv>
#include <chrono>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <vector>
using namespace iris::noc;
namespace {
std::uint64_t number(std::istringstream& s) {
 std::string t; if (!(s>>t)) throw std::invalid_argument("Incomplete physical boundary");
 std::uint64_t v=0; auto p=std::from_chars(t.data(),t.data()+t.size(),v);
 if(p.ec!=std::errc{}||p.ptr!=t.data()+t.size())throw std::invalid_argument("Unsigned integer required");return v;
}
std::uint8_t small(std::istringstream& s){auto v=number(s);if(v>255)throw std::invalid_argument("Field exceeds8bits");return v;}
bool flag(std::istringstream& s){auto v=number(s);if(v>1)throw std::invalid_argument("Boolean required");return v;}
FullPayload payload(std::istringstream& s){FullPayload p{};for(auto& w:p.words){auto v=number(s);if(v>0xffffffffULL)throw std::invalid_argument("Payload exceeds32bits");w=v;}return p;}
FullChannelFlit channel(std::istringstream& s){FullChannelFlit f{};f.valid=flag(s);f.head=flag(s);f.tail=flag(s);f.payload=payload(s);f.flow={small(s),small(s),small(s),small(s),small(s)};f.vc=small(s);return f;}
struct Record{std::uint64_t tb;FullRouterInputs input;};
std::vector<Record> read(const std::string& path){
 std::ifstream file(path);if(!file)throw std::invalid_argument("Trace unavailable");std::vector<Record> rows;
 for(std::string line;std::getline(file,line);){std::istringstream s(line);std::string op;if(!(s>>op))continue;if(op!="step")throw std::invalid_argument("Benchmark accepts physical steps only");
  Record r{};r.tb=number(s);auto& i=r.input;i.reset=flag(s);for(auto& f:i.from_network)f=channel(s);
  for(auto& f:i.from_local){f.valid=flag(s);f.head=flag(s);f.tail=flag(s);f.payload=payload(s);f.egress_id=small(s);}
  for(auto& c:i.downstream)c={small(s),small(s)};i.local_ready=flag(s);std::string extra;if(s>>extra)throw std::invalid_argument("Extra boundary field");rows.push_back(r);
 }
 if(rows.empty()||!rows.front().input.reset)throw std::invalid_argument("Actual-reset trace required");return rows;
}
// FNV-1a over each defined logical field, eight bytes little endian. This is a
// benchmark output-use check; the independent validator compares every field.
void add(std::uint64_t& h,std::uint64_t v){for(unsigned n=0;n<8;n++){h^=(v>>(8*n))&255;h*=1099511628211ULL;}}
void add(std::uint64_t& h,const FullPayload& p){for(auto v:p.words)add(h,v);}
void add(std::uint64_t& h,const FullChannelFlit& f){add(h,f.valid);if(!f.valid)return;add(h,f.head);add(h,f.tail);add(h,f.payload);add(h,f.flow.vnet);add(h,f.flow.ingress_node);add(h,f.flow.ingress_id);add(h,f.flow.egress_node);add(h,f.flow.egress_id);add(h,f.vc);}
std::uint64_t digest(const std::vector<Record>& rows,const std::vector<FullRouterOutputs>& outputs){
 std::uint64_t h=14695981039346656037ULL;
 for(std::size_t n=0;n<rows.size();n++){
  if(rows[n].input.reset)continue;add(h,rows[n].tb);const auto& o=outputs[n];
  for(auto& f:o.to_network)add(h,f);for(bool v:o.local_ready)add(h,v);for(auto& c:o.upstream){add(h,c.credit_return);add(h,c.vc_free);}
  add(h,o.to_local.valid);if(o.to_local.valid){add(h,o.to_local.head);add(h,o.to_local.tail);add(h,o.to_local.payload);}
  for(auto v:o.va_stalls)add(h,v);for(auto v:o.sa_stalls)add(h,v);
 }return h;
}
}
int main(int argc,char** argv){try{
 if(argc!=4)throw std::invalid_argument("Usage: benchmark INPUT REPETITIONS EXPLICIT_SEED");std::istringstream reps_s(argv[2]),seed_s(argv[3]);auto repetitions=number(reps_s),seed=number(seed_s);if(!repetitions||repetitions>100||seed>0xffffffffULL)throw std::invalid_argument("Invalid repetition/seed");
 auto rows=read(argv[1]);std::vector<FullRouterOutputs> outputs(rows.size());FullNode5Router router(seed);
 std::cout<<"{\"source_identity\":\""<<FullNode5Router::source_identity()<<"\",\"edges_per_pass\":"<<rows.size()<<",\"text_io_timed\":false,\"output_vector_store_timed\":true,\"passes\":[";
 std::uint64_t first=0;
 for(std::uint64_t rep=0;rep<repetitions;rep++){
  const auto start=std::chrono::steady_clock::now();for(std::size_t n=0;n<rows.size();n++)outputs[n]=router.step(rows[n].input);
  const auto nanos=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();auto h=digest(rows,outputs);if(rep&&h!=first)throw std::runtime_error("Reset replay digest changed across repetitions");first=h;
  if(rep)std::cout<<',';std::cout<<"{\"native_loop_ns\":"<<nanos<<",\"edges_per_second\":"<<double(rows.size())*1e9/double(nanos)<<",\"defined_output_fnv64\":"<<h<<'}';
 }
 std::cout<<"]}\n";return 0;
}catch(const std::exception& e){std::cerr<<"Benchmark refused: "<<e.what()<<'\n';return 2;}}
