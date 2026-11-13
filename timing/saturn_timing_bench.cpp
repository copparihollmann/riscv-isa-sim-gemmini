#include "saturn_timing.hpp"
#include <bit>
#include <chrono>
#include <cstdio>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <unistd.h>
#include <vector>
using namespace iris::saturn;
int main(int argc,char**argv){try{
 if(argc!=6)throw std::invalid_argument("PROFILE HART input.txt masks.bin repetitions required");Profile profile=std::string(argv[1])=="compute"?Profile::Compute128:std::string(argv[1])=="rocket"?Profile::Rocket256:throw std::invalid_argument("Unknown profile");unsigned hart=std::stoul(argv[2]),reps=std::stoul(argv[5]);if(!reps||reps>7)throw std::invalid_argument("Bounded repetitions1..7 required");std::ifstream input(argv[3]);if(!input)throw std::runtime_error("Input unavailable");std::vector<ReferenceInputs> rows;
 for(std::string line;std::getline(input,line);){std::istringstream s(line);std::string op;std::uint64_t edge;s>>op>>edge;if(op!="step"||edge!=rows.size())throw std::runtime_error("Consecutive physical frames required");ReferenceInputs i;i.words.resize(SaturnTimingCut::input_fields(profile).size());for(auto&v:i.words)if(!(s>>v))throw std::runtime_error("Incomplete physical frame");rows.push_back(std::move(i));}
 static_assert(std::endian::native==std::endian::little);std::ifstream mf(argv[4],std::ios::binary);char magic[8];std::uint64_t mask_rows,mask_width;mf.read(magic,8);mf.read(reinterpret_cast<char*>(&mask_rows),8);mf.read(reinterpret_cast<char*>(&mask_width),8);if(!mf||std::string(magic,8)!="SATMSK01"||mask_rows!=rows.size()||mask_width!=SaturnTimingCut::output_fields(profile).size())throw std::runtime_error("Qualified mask boundary mismatch");std::vector<std::uint64_t> masks(mask_rows*mask_width);mf.read(reinterpret_cast<char*>(masks.data()),masks.size()*8);if(!mf||mf.peek()!=EOF)throw std::runtime_error("Truncated/extra mask bytes");
 auto fs=SaturnTimingCut::input_fields(profile);unsigned ex=0;while(ex<fs.size()&&fs[ex].name!=(profile==Profile::Compute128?"io_ex_valid":"io_core_ex_valid"))++ex;if(ex==fs.size())throw std::runtime_error("Source EX input missing");std::size_t first=0;while(first<rows.size()&&!rows[first].words[ex])++first;if(first==rows.size())throw std::runtime_error("Active workload required");
 std::vector<double> seconds;std::vector<std::uint64_t> mixes,counts;const unsigned seeds[]={0,17,91,3,5,7,11};std::fflush(stdout);int saved=dup(STDOUT_FILENO),nullfd=open("/dev/null",O_WRONLY);if(saved<0||nullfd<0)throw std::runtime_error("Cannot isolate source debug output");
 for(unsigned rep=0;rep<reps;rep++){
  SaturnTimingCut model(profile,hart,seeds[rep],ReferenceScope::ExplicitTwoStateWithExternalDefinedness);std::vector<ReferenceOutputs> results(rows.size()-first);if(dup2(nullfd,STDOUT_FILENO)<0)throw std::runtime_error("Cannot suppress source debug stream");
  // All reset/boot-prefix edges really execute; their host cost is outside the
  // active guest interval. No source state is imported or skipped.
  for(std::size_t edge=0;edge<first;edge++)model.step(rows[edge]);
  auto start=std::chrono::steady_clock::now();for(std::size_t edge=first;edge<rows.size();edge++)results[edge-first]=model.step(rows[edge]);double sec=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();std::fflush(stdout);if(dup2(saved,STDOUT_FILENO)<0)throw std::runtime_error("Cannot restore stdout");
  std::uint64_t mix=1469598103934665603ULL,count=0;for(std::size_t edge=first;edge<rows.size();edge++)for(unsigned field=0;field<mask_width;field++){auto mask=masks[edge*mask_width+field];if(mask){mix^=results[edge-first].words[field]&mask;mix*=1099511628211ULL;++count;}}
  if(model.edges()!=rows.size())throw std::runtime_error("Reference clock count changed");seconds.push_back(sec);mixes.push_back(mix);counts.push_back(count);
 }
 close(saved);close(nullfd);std::cout<<"{\"source_identity\":\""<<SaturnTimingCut::source_identity()<<"\",\"profile\":\""<<argv[1]<<"\",\"hart\":"<<hart<<",\"executed_prefix_edges\":"<<first<<",\"timed_active_guest_edges\":"<<rows.size()-first<<",\"runs\":[";
 for(unsigned n=0;n<seconds.size();n++){if(n)std::cout<<',';std::cout<<"{\"seed\":"<<seeds[n]<<",\"host_seconds\":"<<seconds[n]<<",\"edges_per_second\":"<<(rows.size()-first)/seconds[n]<<",\"qualified_field_mix64\":"<<mixes[n]<<",\"qualified_words\":"<<counts[n]<<'}';}
 std::cout<<"],\"source_debug_prints_discarded_but_formatting_cost_included\":true,\"parsing_masking_digest_textIO_outside_timed_loop\":true,\"source_edges_skipped\":0,\"component_cost_not_SoC_MIPS\":true,\"hardware_contacted\":false}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
