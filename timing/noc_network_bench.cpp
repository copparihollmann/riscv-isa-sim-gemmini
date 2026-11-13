#include "noc_network.hpp"
#include <charconv>
#include <chrono>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <vector>
using namespace iris::noc;
namespace {
std::uint64_t number(std::istringstream& s){std::string t;if(!(s>>t))throw std::invalid_argument("Incomplete physical input");std::uint64_t v=0;auto p=std::from_chars(t.data(),t.data()+t.size(),v);if(p.ec!=std::errc{}||p.ptr!=t.data()+t.size())throw std::invalid_argument("Unsigned integer required");return v;}
struct Row{std::uint64_t tb;NetworkInputs i;};
std::vector<Row> read(const std::string& path){std::ifstream f(path);if(!f)throw std::invalid_argument("Physical input unavailable");std::vector<Row> rows;for(std::string line;std::getline(f,line);){std::istringstream s(line);std::string op;if(!(s>>op))continue;if(op!="step")throw std::invalid_argument("Benchmark requires physical step stream");Row r{};r.tb=number(s);for(auto& x:r.i.values)x=number(s);std::string extra;if(s>>extra)throw std::invalid_argument("Extra TL fields");rows.push_back(r);}if(rows.empty()||rows[0].i.values[165]!=1)throw std::invalid_argument("Actual reset stream required");return rows;}
std::uint64_t mix(const std::vector<Row>& rows,const std::vector<NetworkOutputs>& outputs){
 auto fields=IrisNoCNetwork::output_fields();std::vector<int> valid(fields.size(),-1);for(std::size_t n=0;n<fields.size();n++){auto pos=fields[n].name.find("_bits_");if(pos==std::string_view::npos)continue;auto target=std::string(fields[n].name.substr(0,pos))+"_valid";for(std::size_t k=0;k<fields.size();k++)if(fields[k].name==target)valid[n]=k;if(valid[n]<0)throw std::logic_error("Missing field validity");}
 std::uint64_t h=14695981039346656037ULL;auto add=[&](std::uint64_t v){h=(h^v)*1099511628211ULL;};
 for(std::size_t n=0;n<rows.size();n++){if(rows[n].i.values[165])continue;add(rows[n].tb);for(std::size_t k=0;k<fields.size();k++)if(valid[k]<0||outputs[n].values[valid[k]])add(outputs[n].values[k]);}return h;
}
template<class F>void refused(F f,unsigned& checks){try{f();}catch(const std::logic_error&){++checks;return;}throw std::runtime_error("Invalid lifecycle operation was accepted");}
void selftest(const std::vector<Row>& rows,const std::filesystem::path& path){
 if(rows.size()<800)throw std::invalid_argument("Longer actual trace needed");IrisNoCNetwork n(1);unsigned checks=0;refused([&]{n.sample();},checks);refused([&]{n.commit();},checks);refused([&]{n.save(path);},checks);
 for(unsigned k=0;k<200;k++)n.step(rows[k].i);n.evaluate(rows[200].i);auto before=n.sample();auto invalid=rows[200].i;auto fields=n.input_fields();std::size_t index=0;while(fields[index].width==64)++index;invalid.values[index]=std::uint64_t{1}<<fields[index].width;
 try{n.evaluate(invalid);}catch(const std::invalid_argument&){++checks;}if(checks!=4)throw std::runtime_error("Width error not refused");refused([&]{n.sample();},checks);refused([&]{n.commit();},checks);if(n.edges()!=200)throw std::runtime_error("Failed evaluate advanced an edge");n.evaluate(rows[200].i);if(n.sample().values!=before.values)throw std::runtime_error("Failed evaluate changed model state");n.commit();refused([&]{n.commit();},checks);refused([&]{n.sample();},checks);n.save(path);IrisNoCNetwork restored(42);restored.restore(path);if(restored.edges()!=201)throw std::runtime_error("Snapshot edge identity");
 for(unsigned k=201;k<800;k++)if(n.step(rows[k].i).values!=restored.step(rows[k].i).values)throw std::runtime_error("Snapshot continuation mismatch");
 std::cout<<"{\"pass\":true,\"lifecycle_rejections\":"<<checks<<",\"snapshot_continuation_edges\":599,\"invalid_evaluate_state_unchanged\":true}\n";
}
}
int main(int argc,char** argv){try{
 if(argc==4&&std::string(argv[1])=="selftest"){selftest(read(argv[2]),argv[3]);return 0;}
 if(argc!=5)throw std::invalid_argument("Usage: benchmark INPUT REPETITIONS EXPLICIT_SEED step|revised");std::istringstream reps_text(argv[2]),seed_text(argv[3]);auto reps=number(reps_text),seed=number(seed_text);if(!reps||reps>100||seed>0xffffffffULL)throw std::invalid_argument("Invalid repetitions/seed");bool revised=std::string(argv[4])=="revised";if(!revised&&std::string(argv[4])!="step")throw std::invalid_argument("Unknown benchmark mode");auto rows=read(argv[1]);std::vector<NetworkOutputs> outputs(rows.size());IrisNoCNetwork network(seed);std::vector<std::size_t> ready_fields;auto in_fields=network.input_fields();for(std::size_t k=0;k<in_fields.size();k++)if(in_fields[k].name.ends_with("_ready"))ready_fields.push_back(k);
 std::cout<<"{\"source_identity\":\""<<IrisNoCNetwork::source_identity()<<"\",\"edges_per_pass\":"<<rows.size()<<",\"text_io_timed\":false,\"output_stores_timed\":true,\"ready_revision_mode\":"<<(revised?"true":"false")<<",\"revised_ready_fields\":"<<ready_fields.size()<<",\"digest\":\"ordered64 field xor-multiply, reset/inactive payload excluded\",\"passes\":[";std::uint64_t first=0;
 for(std::uint64_t rep=0;rep<reps;rep++){
  auto start=std::chrono::steady_clock::now();for(std::size_t n=0;n<rows.size();n++){
   if(!revised){outputs[n]=network.step(rows[n].i);continue;}
   network.evaluate(rows[n].i);auto original=network.sample();auto changed=rows[n].i;for(auto field:ready_fields)changed.values[field]^=1;network.evaluate(changed);network.sample();network.evaluate(rows[n].i);outputs[n]=network.sample();if(outputs[n].values!=original.values)throw std::runtime_error("Same-edge readiness revision changed persistent state");network.commit();
  }auto ns=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();auto h=mix(rows,outputs);if(rep&&h!=first)throw std::runtime_error("Repeated reset replay changed defined outputs");first=h;if(rep)std::cout<<',';std::cout<<"{\"native_loop_ns\":"<<ns<<",\"edges_per_second\":"<<double(rows.size())*1e9/double(ns)<<",\"defined_field_mix64\":"<<h<<'}';
 }std::cout<<"]}\n";return 0;
}catch(const std::exception& e){std::cerr<<"Network benchmark refused: "<<e.what()<<'\n';return 2;}}
