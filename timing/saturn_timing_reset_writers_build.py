#!/usr/bin/env python3
"""Observe early no-read writers versus real VRF reset sweep, with accepted-write ledger."""
import argparse,hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);native=R/'build/saturn-timing-native-v1';sdk=R/'build/saturn-timing-sdk-v1';base=(R/'timing/saturn_timing_scrub.cpp').read_text().split('template<class M>static void run',1)[0];code=base+'\n#include <deque>\n#include <set>\n#include <vector>\nstruct BankWrite{unsigned eg;std::vector<std::uint32_t> data,mask;};\n'
 for profile,model,top,banks,dlen in [('compute','VSaturnCompute','SaturnShuttleUnit',4,128),('rocket','VSaturnRocket','SaturnRocketUnit',1,256)]:
  core='io_core_'if profile=='rocket'else'io_';root=(native/profile/'model'/(model+'___024root.h')).read_text();prefix=top+'__DOT__vu__DOT__vrf__DOT__vrf__DOT__'
  code+='static std::vector<BankWrite> physical_writes('+model+'&m){std::vector<BankWrite> v;\n'
  for bank in range(banks):
   member=prefix+'vrf_'+str(bank)+'__DOT__';assert all(member+f in root for f in ['write_valid','write_bits_eg','write_bits_data','write_bits_mask']);code+='if(m.rootp->'+member+'write_valid){BankWrite w;w.eg=unsigned(m.rootp->'+member+'write_bits_eg)*'+str(banks)+'+'+str(bank)+';'
   for n in range(dlen//32):code+='w.data.push_back(m.rootp->'+member+'write_bits_data['+str(n)+']);w.mask.push_back(m.rootp->'+member+'write_bits_mask['+str(n)+']);'
   code+='v.push_back(w);}\n'
  code+='return v;}\n'
  code+='static void send('+model+'&m,unsigned kind,bool valid){command(m,valid);m.'+core+'ex_vconfig_vtype_vlmul_mag=kind==3?0:3;'
  inst='io_core_ex_inst'if profile=='rocket'else'io_ex_uop_inst';rs1='io_core_ex_rs1'if profile=='rocket'else'io_ex_uop_rs1_data';code+='if(kind<3){m.'+core+'ex_vconfig_vl=256;m.'+core+'ex_vconfig_vtype_vsew=0;m.'+inst+'=kind==0?0x5e03b457u:kind==1?0x5e02c457u:0x02050407u;m.'+rs1+'=kind==2?0x80010000ULL:7ULL;}else m.'+rs1+'=0;'
  if profile=='compute':code+='m.io_mem_tlb_req_ready=1;m.io_mem_tlb_resp_paddr=0x80010000ULL;'
  else:code+='m.io_tlb_s1_resp_paddr=0x80010000ULL;'
  code+='}\nstatic bool exready('+model+'&m){return m.'+core+'ex_ready;}\nstatic std::uint64_t scalar('+model+'&m){return m.'+core+'resp_bits_data;}\n'
  # Pure external fixture; incoming D metadata/data never touches internal state.
  code+='static void data('+model+'&m,bool valid,unsigned tag,unsigned size){m.auto_atl_out_a_ready=1;m.auto_atl_out_d_valid=valid;m.auto_atl_out_d_bits_opcode=1;m.auto_atl_out_d_bits_source=tag;m.auto_atl_out_d_bits_size=size;'
  if profile=='compute':code+='for(unsigned n=0;n<8;n++)m.auto_atl_out_d_bits_data[n]=0x07070707u;'
  else:code+='m.auto_atl_out_d_bits_data=0x0707070707070707ULL;'
  code+='}\n'
 code+='''struct Reply{unsigned source,size,left;};
 template<class M>static void run(const char*profile,unsigned egs,unsigned dlen,unsigned bus,unsigned kind,unsigned seed,bool corrupt){
 auto ctx=std::make_unique<VerilatedContext>();ctx->threads(1);ctx->randSeed(seed);ctx->randReset(2);M m(ctx.get());inputs(m);m.reset=1;m.clock=0;m.eval();for(unsigned n=0;n<2;n++){m.clock=1;m.eval();m.clock=0;m.eval();}m.reset=0;
 std::vector<std::vector<std::uint32_t>> shadow(egs,std::vector<std::uint32_t>(dlen/32)),known(egs,std::vector<std::uint32_t>(dlen/32));for(unsigned eg=0;eg<egs;eg++)for(unsigned w=0;w<dlen/32;w++)shadow[eg][w]=ram(m,eg,w);
 std::deque<Reply> replies;std::set<unsigned> scrubbed,produced;unsigned writes_total=0,scrub_done=~0u,first_producer=~0u,reader_response=~0u;std::uint64_t readback=0,expected_readback=0;bool reader_sent=false,mutated=false;
 for(unsigned edge=0;edge<egs+160;edge++){
  bool reader=edge==egs+100;send(m,reader?3:kind,edge==0||reader);if(reader){reader_sent=true;unsigned target=8*(256/dlen);expected_readback=std::uint64_t(shadow[target][0])|(std::uint64_t(shadow[target][1])<<32);}
  data(m,!replies.empty(),replies.empty()?0:replies.front().source,replies.empty()?0:replies.front().size);m.eval();auto state=sweep(m);if(edge==0||reader)require(exready(m),"Fixture did not obey physical EX acceptance");if(!state.active&&scrub_done==~0u)scrub_done=edge;
  if(response(m)){require(reader_sent,"Unexpected scalar response before reader");require(reader_response==~0u,"Repeated scalar response");require(scalar(m)==expected_readback,"Architectural readback disagrees with exact accepted-write order");reader_response=edge;readback=scalar(m);}
  auto accepted=physical_writes(m);
  for(auto write:accepted){require(write.eg<egs,"Actual bank write address out of bounds");bool zero=true,seven=true;for(unsigned w=0;w<dlen/32;w++){zero&=write.data[w]==0;seven&=write.data[w]==0x07070707u;}require(zero||seven,"Unexpected writer data in zero/seven fixture");if(zero)scrubbed.insert(write.eg);if(seven){produced.insert(write.eg);if(first_producer==~0u)first_producer=edge;}
   std::cout<<"RESET_WRITE "<<profile<<','<<kind<<','<<seed<<','<<edge<<','<<unsigned(state.active)<<','<<state.cursor<<','<<write.eg<<','<<(zero?0:7);for(unsigned w=0;w<dlen/32;w++)std::cout<<','<<write.mask[w];std::cout<<'\\n';
   if(corrupt&&seven&&!mutated){write.data[0]^=1;mutated=true;}
   for(unsigned w=0;w<dlen/32;w++){shadow[write.eg][w]=(shadow[write.eg][w]&~write.mask[w])|(write.data[w]&write.mask[w]);known[write.eg][w]|=write.mask[w];}++writes_total;
  }
  bool dpop=m.auto_atl_out_d_valid&&m.auto_atl_out_d_ready;bool apush=m.auto_atl_out_a_valid&&m.auto_atl_out_a_ready;Reply incoming{};
  if(apush){require(m.auto_atl_out_a_bits_opcode==4,"Unexpected non-Get in pure-load fixture");incoming={unsigned(m.auto_atl_out_a_bits_source),unsigned(m.auto_atl_out_a_bits_size),unsigned(((1ULL<<m.auto_atl_out_a_bits_size)+bus-1)/bus)};}
  m.clock=1;m.eval();m.clock=0;m.eval();for(unsigned eg=0;eg<egs;eg++)for(unsigned w=0;w<dlen/32;w++)require(ram(m,eg,w)==shadow[eg][w],"Accepted bank-write transcript does not explain physical VRF transition");
  if(dpop){require(!replies.empty(),"Fixture D without A");if(--replies.front().left==0)replies.pop_front();}if(apush)replies.push_back(incoming);
 }
 unsigned zero_words=0,seven_words=0,unknown_words=0;for(unsigned eg=0;eg<egs;eg++)for(unsigned w=0;w<dlen/32;w++){unknown_words+=known[eg][w]!=0xffffffffu;if(eg>=8*(256/dlen)&&eg<16*(256/dlen)){zero_words+=shadow[eg][w]==0;seven_words+=shadow[eg][w]==0x07070707u;}}
 require(replies.empty()&&reader_response!=~0u,"Early writer/reader did not drain");
 std::cout<<"RESET_WRITER_RESULT {\\"profile\\":\\""<<profile<<"\\",\\"kind\\":"<<kind<<",\\"seed\\":"<<seed<<",\\"scrub_flag_clear_edge\\":"<<scrub_done<<",\\"first_nonzero_write_edge\\":"<<first_producer<<",\\"scrubbed_EGs_seen\\":"<<scrubbed.size()<<",\\"producer_EGs_seen\\":"<<produced.size()<<",\\"physical_writes\\":"<<writes_total<<",\\"destination_zero_words\\":"<<zero_words<<",\\"destination_seven_words\\":"<<seven_words<<",\\"unwritten_unknown_words\\":"<<unknown_words<<",\\"scalar_readback\\":"<<readback<<",\\"reader_response_edge\\":"<<reader_response<<"}\\n";
 }
 int main(int argc,char**argv){try{bool corrupt=argc==2&&std::string(argv[1])=="--corrupt-ledger";for(unsigned seed:{0u,17u})for(unsigned kind=0;kind<3;kind++){run<VSaturnCompute>("compute",64,128,32,kind,seed,corrupt);run<VSaturnRocket>("rocket",32,256,8,kind,seed,corrupt);}return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\\n';return 2;}}
''';source=R/'timing/saturn_timing_reset_writers.cpp';source.write_text(code);tool=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include');command=['/usr/bin/g++','-O3','-std=c++20','-I'+str(tool),'-I'+str(tool/'vltstd')]+['-I'+str(native/k/'model')for k in ['compute','rocket']]+[str(source),str(sdk/'sdk/libiris_saturn_timing.a'),'-pthread','-latomic','-o',str(out/'early-writers')]
 with(out/'build.log').open('w')as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
 q=subprocess.run([str(out/'early-writers')],capture_output=True,text=True,timeout=60);(out/'stdout').write_text(q.stdout);(out/'stderr').write_text(q.stderr)
 if q.returncode:raise RuntimeError('Preserved early writer test failed; inspect exact source/output')
 results=[json.loads(x.split(' ',1)[1])for x in q.stdout.splitlines()if x.startswith('RESET_WRITER_RESULT ')];assert len(results)==12;bad=subprocess.run([str(out/'early-writers'),'--corrupt-ledger'],capture_output=True,text=True,timeout=60);(out/'corrupt-ledger.stderr').write_text(bad.stderr);assert bad.returncode==2
 report={'schema':'iris.saturn_early_reset_writer_observation.v1','argv':command,'results':results,'input_sha256':{str(p):sha(p)for p in[Path(__file__),source,R/'timing/saturn_timing_scrub.cpp',sdk/'build.json',sdk/'sdk/libiris_saturn_timing.a']},'native_sha256':sha(out/'early-writers'),'internal_state_injection':False,'external_load_fixture':'ATL Aready1, ordered Get replies begin at following source edge; one busbeat per accepted D edge, byte pattern7. Explicit fixture, not a physical memory latency model.','wrong_accepted_write_ledger_rejected':True,'hardware_contacted':False,'matches_Ethan_image':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'results':results,'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
