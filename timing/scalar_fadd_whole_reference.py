#!/usr/bin/env python3
"""Relink frozen saved whole-RTL objects with a bounded read-only FP observer."""
import argparse,hashlib,json,re,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);base=ROOT/'build/vme-column-preload-reference-v1';receipt=json.loads((base/'build.json').read_text());text=(base/'main.cc').read_text();header=Path(next(x[2:]for x in receipt['compile_argv']if x.startswith('-I')and x.endswith('/model')))/'VTestDriver___024root.h';decl=header.read_text();prefix='TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__'
 cores=[prefix+'tile_prci_domain'+(''if h==0 else'_'+str(h))+'__DOT__element_reset_domain_'+('shuttle_tile'if h<2 else'rockettile')+'__DOT__core__DOT__'for h in range(3)];fpu=prefix+'tile_prci_domain_2__DOT__element_reset_domain_rockettile__DOT__fpuOpt__DOT__'
 used=[]
 def field(n):
  if not re.search(r'\b'+re.escape(n)+r'\s*[;\[]',decl):raise ValueError('Missing actual readonly field '+n)
  used.append(n);return 'r->'+n
 def c(h,s):return field(cores[h]+s)
 def fp(s):return field(fpu+s)
 observer='''\nstruct FPObs {bool reset=true,ex=false,write=false,retire=false;uint64_t pc=0,epc=0,value=0,cycle=0,ir=0;uint32_t raw=0,exraw=0;unsigned rd=0,ready=0;uint32_t rf[3]{},operand[3]{};};\nstatic FPObs previous[3];static bool previous_clock[3]{};static uint64_t source_edges[3]{};static unsigned moves=0,counter_reads=0;static uint64_t whole_edges=0;\nstatic bool isadd(uint32_t x){return (x&0xfe00007f)==0x53||(x&0xfe00007f)==0x02000053||(x&0xfe00007f)==0x04000053;}\nstatic bool ismove(uint32_t x){return (x&0xfff0707f)==0xe0000053||(x&0xfff0707f)==0xe2000053||(x&0xfff0707f)==0xe4000053;}\nstatic bool observe_FP(VTestDriver___024root*r){\n bool clocks[3]={r->TestDriver__DOT__testHarness__DOT__source__DOT__clk_i,r->TestDriver__DOT__testHarness__DOT__source__DOT__clk_i,r->TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__chipyard_prcictrl_domain__DOT___clock_gater_auto_clock_gater_out_member_allClocks_tileClockGroup_rockettile_2_clock};\n'''
 for h in range(3):
  observer+=' if(!clocks['+str(h)+']){auto&x=previous['+str(h)+'];x.reset=r->TestDriver__DOT__reset||'+field(prefix+'tile_prci_domain'+(''if h==0 else'_'+str(h))+'__DOT__element_reset_domain_'+('shuttle_tile'if h<2 else'rockettile')+'__DOT__vector_unit__DOT__reset')+';\n'
  if h<2:
   observer+='x.ex='+c(h,'__Vcellinp__fp_pipe__io_in_valid')+';x.exraw='+c(h,'ex_uops_reg_0_bits_inst')+';x.epc='+c(h,'ex_uops_reg_0_bits_pc')+';\n'
   observer+='x.write='+c(h,'fp_pipe__DOT__io_out_valid_r_3')+'&&!'+c(h,'fp_pipe__DOT__io_out_valid_r_6')+'&&!'+c(h,'fp_pipe__DOT__io_out_valid_r_8')+';x.rd='+c(h,'fp_pipe__DOT__io_out_rd_r_3')+';x.ready='+c(h,'fsboard_0')+';\n'
   observer+='x.retire='+c(h,'com_retire_0')+';x.raw='+c(h,'com_uops_reg_0_bits_inst')+';x.pc='+c(h,'com_uops_reg_0_bits_pc')+';x.value='+c(h,'com_uops_reg_0_bits_wdata_bits')+';\n'
   observer+='for(unsigned k=0;k<3;++k){x.rf[k]='+c(h,'fregfile_0')+'[k];x.operand[k]='+c(h,'fp_pipe_io_frs1_data')+'[k];}\n'
  else:
   observer+='x.ex='+fp('req_valid')+';x.exraw='+fp('ex_reg_inst')+';x.epc='+c(h,'ex_reg_pc')+';x.write=('+fp('wen')+'&1)&&!'+fp('wbInfo_0_cp')+';x.rd='+fp('wbInfo_0_rd')+';\n'
   observer+='x.retire='+c(h,'wb_valid')+';x.raw='+c(h,'wb_reg_inst')+';x.pc='+c(h,'wb_reg_pc')+';x.value='+c(h,'wb_reg_wdata')+';\n'
   observer+='for(unsigned k=0;k<3;++k){x.rf[k]='+fp('regfile_ext__DOT__Memory')+'[0][k];x.operand[k]='+fp('regfile_ext__DOT__Memory')+'['+fp('ex_ra_0')+'][k];}\n'
  observer+='x.cycle=('+c(h,'csr__DOT__large_1')+'<<6)|'+c(h,'csr__DOT__small_1')+';x.ir=('+c(h,'csr__DOT__large_0')+'<<6)|'+c(h,'csr__DOT__small_0')+';}\n'
 observer+=''' ++whole_edges;for(unsigned h=0;h<3;++h){bool fire=clocks[h]&&!previous_clock[h];previous_clock[h]=clocks[h];if(!fire)continue;++source_edges[h];const auto&x=previous[h];if(x.reset)continue;\n if(x.ex&&isadd(x.exraw)&&x.epc>=0x80000000ull){fprintf(stderr,"SCALAR_RTL_EX {\\\"hart\\\":%u,\\\"edge\\\":%lu,\\\"cycle\\\":%lu,\\\"pc\\\":%lu,\\\"raw\\\":%u,\\\"ready0_before\\\":%u,\\\"rf0_before\\\":[%u,%u,%u],\\\"operand1\\\":[%u,%u,%u]}\\n",h,source_edges[h],x.cycle,x.epc,x.exraw,x.ready,x.rf[0],x.rf[1],x.rf[2],x.operand[0],x.operand[1],x.operand[2]);}\n if(x.write){fprintf(stderr,"SCALAR_RTL_WRITE {\\\"hart\\\":%u,\\\"edge\\\":%lu,\\\"rd\\\":%u,\\\"ready0_before\\\":%u,\\\"rf0_before\\\":[%u,%u,%u]}\\n",h,source_edges[h],x.rd,x.ready,x.rf[0],x.rf[1],x.rf[2]);}\n if(x.retire&&x.pc>=0x80000000ull){const auto csr=x.raw>>20; if((x.raw&127)==0x73&&(csr==0xb00||csr==0xb02)){++counter_reads;fprintf(stderr,"SCALAR_RTL_COUNTER {\\\"hart\\\":%u,\\\"edge\\\":%lu,\\\"pc\\\":%lu,\\\"raw\\\":%u,\\\"csr\\\":%u,\\\"value\\\":%lu}\\n",h,source_edges[h],x.pc,x.raw,csr,csr==0xb00?x.cycle:x.ir);}\n if(ismove(x.raw)){++moves;fprintf(stderr,"SCALAR_RTL_READOUT {\\\"hart\\\":%u,\\\"edge\\\":%lu,\\\"pc\\\":%lu,\\\"raw\\\":%u,\\\"bits\\\":%lu}\\n",h,source_edges[h],x.pc,x.raw,x.value);}}\n } if(moves>=9&&counter_reads>=36){fprintf(stderr,"SCALAR_RTL_OBSERVER_DONE moves=%u counters=%u edge=%lu\\n",moves,counter_reads,whole_edges);return true;}return false;\n}\n'''
 # Python emits escaped C-string delimiters only; all target accesses are reads.
 observer=observer.replace('\\\\\\"','\\"')
 text=text.replace('//======================',observer+'\n//======================',1);text=text.replace('        topp->eval();','        topp->eval();\n        if(observe_FP(iris_root))break;',1)
 source=out/'main.cc';source.write_text(text);comp=receipt['compile_argv'][:];comp[comp.index('-c')+1]=str(source);comp[comp.index('-o')+1]=str(out/'main.o');comp[comp.index('-MF')+1]=str(out/'main.d');link=receipt['link_argv'][:];link[1]=str(out/'main.o');link[link.index('-o')+1]=str(out/'simulator-preload');started=time.monotonic()
 for name,argv in [('compile',comp),('link',link)]:
  q=subprocess.run(argv,capture_output=True);(out/(name+'.stdout')).write_bytes(q.stdout);(out/(name+'.stderr')).write_bytes(q.stderr)
  if q.returncode:raise RuntimeError('host '+name+' failed')
 inputs={str(base/'build.json'):sha(base/'build.json'),str(base/'main.cc'):sha(base/'main.cc'),str(source):sha(source),str(header):sha(header),str(Path(__file__).resolve()):sha(Path(__file__).resolve())}
 for path,d in receipt['input_sha256'].items():
  if sha(Path(path))!=d:raise ValueError('Frozen reference input changed '+path)
  inputs[path]=d
 for token in link:
  f=Path(token)
  if f.is_file():inputs[str(f)]=sha(f)
 result=dict(schema='iris.scalar_fadd_readonly_whole_reference.v1',status='built',compile_argv=comp,link_argv=link,input_sha256=inputs,binary_sha256=sha(out/'simulator-preload'),source_FIR_sha256=receipt['source_fir_sha256'],all_target_RTL_objects_unchanged=True,internal_state_driven=False,read_only_fields=sorted(set(used)),host_seconds=time.monotonic()-started,source_image_association_verified=False,hardware_contacted=False);(out/'build.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':'built','host_seconds':result['host_seconds'],'binary_sha256':result['binary_sha256']}))
if __name__=='__main__':main()
