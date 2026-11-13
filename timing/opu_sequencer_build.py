#!/usr/bin/env python3
"""Build the exact saved two-module OPU controller, with explicit edge phases."""
import argparse,hashlib,json,os,re,shutil,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ports(path):
 s=path.read_text().split('module OuterProductSequencer(',1)[1].split('\n);',1)[0]
 s='\n'.join(line.split('//')[0]for line in s.splitlines())
 return [{'direction':d,'width':int(msb)+1 if msb else 1,'port':n} for d,msb,n in re.findall(r'\b(input|output)\s+(?:\[(\d+):0\]\s+)?(\w+)\s*[,\n]',s+'\n') if n!='clock']
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--jobs',type=int,default=4);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 rtl=R/'build/rtl-verilator';manifest=json.loads((rtl/'manifest.json').read_text());files=[rtl/'gen-collateral'/n for n in ['OuterProductSequencer.sv','PipeScheduler.sv']]
 for f in files:
  if sha(f)!=manifest['sim_source_sha256'][str(f)]:raise ValueError('Saved RTL changed: '+str(f))
 (out/'rtl').mkdir()
 for f in files:shutil.copy2(f,out/'rtl'/f.name)
 profile=ports(files[0]);fields={}
 for d in ['input','output']:
  fs=[]
  for f in profile:
   if f['direction']!=d:continue
   for lo in range(0,f['width'],64):fs.append(dict(f,index=len(fs),lo=lo,width=min(64,f['width']-lo),name=f['port']+('_hi' if lo else ''),physical_width=f['width']))
  fields[d]=fs
 (out/'ports.json').write_text(json.dumps(fields,indent=2)+'\n')
 schema='#pragma once\n#include <cstddef>\nnamespace iris::opu {\n'
 for d in fields:schema+='inline constexpr std::size_t sequencer_'+d+'_count='+str(len(fields[d]))+';\n'
 schema+='}\n';(R/'timing/opu_sequencer_schema.hpp').write_text(schema)
 code='''#include "opu_sequencer.hpp"
#include "opu_sequencer_identity.hpp"
#include "VOPUSequencer.h"
#include "verilated.h"
#include <stdexcept>
namespace iris::opu {
struct IrisOPUSequencer::Impl {
 std::unique_ptr<VerilatedContext> context;std::unique_ptr<VOPUSequencer> model;
 std::uint64_t edge_count=0;bool evaluated=false,reset_seen=false,dispatch_seen=false;
 explicit Impl(std::uint32_t seed):context(std::make_unique<VerilatedContext>()){
  context->threads(1);context->randSeed(seed);context->randReset(2);
  model=std::make_unique<VOPUSequencer>(context.get());model->clock=0;
 }
};
IrisOPUSequencer::IrisOPUSequencer(std::uint32_t seed):impl_(std::make_unique<Impl>(seed)){}
IrisOPUSequencer::~IrisOPUSequencer()=default;
IrisOPUSequencer::IrisOPUSequencer(IrisOPUSequencer&&)noexcept=default;
IrisOPUSequencer& IrisOPUSequencer::operator=(IrisOPUSequencer&&)noexcept=default;
void IrisOPUSequencer::evaluate(const SequencerInputs&i){
 impl_->evaluated=false;auto&m=*impl_->model;
'''
 for f in fields['input']:
  if f['width']<64:code+='if(i.values['+str(f['index'])+']>='+str(1<<f['width'])+'ULL)throw std::invalid_argument("OPU field exceeds width: '+f['port']+'");\n'
 ix={f['port']:'i.values['+str(f['index'])+']'for f in fields['input']}
 code+='const auto bits='+ix['io_dis_bits_bits']+', sew='+ix['io_dis_bits_vconfig_vtype_vsew']+';\n'
 code+='''auto key=bits&0xfc00707fULL;
 bool mm=(key==0xf0000077ULL||key==0xf0001077ULL);
 bool mvin=key==0x5c006057ULL;
 bool mvout=(bits&0xfdf0707fULL)==0x41f06057ULL;
 bool zero=(bits&0xfdfff07fULL)==0x41e06057ULL;
 bool discard=(bits&0xfdfff07fULL)==0x41c06057ULL;
'''
 code+='if('+ix['io_dis_valid']+'){\n'
 code+='if('+ix['reset']+')throw std::invalid_argument("Dispatch while reset asserted is outside qualified ABI");\n'
 code+='if(!impl_->reset_seen)throw std::invalid_argument("Physical reset required before dispatch");\n'
 code+='if(!(mm||mvin||mvout||zero||discard)|| (mm&&sew!=0)||((mvin||mvout)&&sew!=2))throw std::invalid_argument("Instruction not accepted by saved OPU dispatcher profile");\n'
 code+='if('+ix['io_dis_bits_vconfig_vl']+'>32||'+ix['io_dis_bits_vconfig_vtype_tm']+'>32||'+ix['io_dis_bits_vconfig_vtype_tk']+'>4)throw std::invalid_argument("Matrix geometry exceeds source-clamped tile profile");\n'
 code+='if(key==0xf0001077ULL&&'+ix['io_dis_bits_rm']+'>4)throw std::invalid_argument("FP8 rounding mode must be resolved legal architectural frm");\n'
 code+='}\n'
 for f in fields['input']:code+='m.'+f['port']+'='+ix[f['port']]+';\n'
 code+='m.clock=0;m.eval();impl_->evaluated=true;\n}\nSequencerOutputs IrisOPUSequencer::sample()const{\nif(!impl_->evaluated)throw std::logic_error("OPU sample requires fresh evaluate");const auto&m=*impl_->model;SequencerOutputs o{};\n'
 always=['io_dis_ready','io_seq_hazard_valid','io_busy','io_iss_valid','io_rvs1_valid','io_rvs2_valid','io_pipe_write_req_request','io_pipe_write_req_fire','io_write_valid','io_write_reg_enable','io_wsboard']
 for f in fields['output']:
  val='m.'+f['port']
  if f['physical_width']>64:val='(std::uint64_t{'+val+'['+str(f['lo']//32)+']}|(std::uint64_t{'+val+'['+str(f['lo']//32+1)+']}<<32))'
  known='impl_->dispatch_seen'
  if f['port'] in always or re.fullmatch(r'io_iss_bits_(?:mrf_idx|row_idx|col_idx|macc|zero|shift|mvin|mvin_col)_\d+',f['port']):known='true'
  if f['port'] in ['io_write_bits','io_write_mask']:known='bool(m.io_write_valid)'
  code+='o.values['+str(f['index'])+']='+val+';o.defined['+str(f['index'])+']=impl_->reset_seen&&('+known+');\n'
 code+='''return o;
}
void IrisOPUSequencer::commit(){
 if(!impl_->evaluated)throw std::logic_error("OPU commit requires fresh evaluate");auto&m=*impl_->model;
 if(m.reset){impl_->reset_seen=true;impl_->dispatch_seen=false;}
 else if(m.io_dis_ready&&m.io_dis_valid)impl_->dispatch_seen=true;
 m.clock=1;m.eval();m.clock=0;m.eval();++impl_->edge_count;impl_->evaluated=false;
}
SequencerOutputs IrisOPUSequencer::step(const SequencerInputs&i){evaluate(i);auto o=sample();commit();return o;}
std::uint64_t IrisOPUSequencer::edges()const{return impl_->edge_count;}
const char* IrisOPUSequencer::source_identity(){return IRIS_OPU_SEQUENCER_SOURCE_ID;}
'''
 for d,fs in fields.items():code+='std::span<const SequencerField> IrisOPUSequencer::'+d+'_fields(){static constexpr SequencerField f[]={'+','.join('{'+json.dumps(f['name'])+','+str(f['width'])+'}'for f in fs)+'};return f;}\n'
 code+='}\n';(R/'timing/opu_sequencer.cpp').write_text(code)
 tool=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator');src=[R/'timing'/('opu_sequencer'+s)for s in ['.cpp','.hpp','_schema.hpp','_driver.cpp','_build.py']]+files+[rtl/'manifest.json',R/'hardware/manifest.json',R/'hardware/evidence/outer-product-sequencer.scala',R/'hardware/evidence/saturn-decode.scala',R/'hardware/evidence/saturn-parameters.scala',R/'third_party/saturn/src/main/scala/common/PipeScheduler.scala',R/'third_party/rocket-chip/src/main/scala/rocket/Matrix.scala',R/'third_party/saturn/src/main/scala/exu/OuterProductUnit.scala',tool,tool.with_name('verilator_bin'),Path('/usr/bin/g++')]
 identity=hashlib.sha256(json.dumps({str(p):sha(p)for p in src},sort_keys=True).encode()).hexdigest();(R/'timing/opu_sequencer_identity.hpp').write_text('#pragma once\n#define IRIS_OPU_SEQUENCER_SOURCE_ID "'+identity+'"\n');src.append(R/'timing/opu_sequencer_identity.hpp')
 command=[str(tool.with_name('perl')),str(tool),'--cc','--exe','--build','-j',str(a.jobs),'--top-module','OuterProductSequencer','--prefix','VOPUSequencer','--assert','-Wno-fatal','--x-initial','unique','--x-assign','unique','--Mdir',str(out/'model'),'+define+RANDOMIZE_REG_INIT',str(out/'rtl/OuterProductSequencer.sv'),str(out/'rtl/PipeScheduler.sv'),str(R/'timing/opu_sequencer.cpp'),str(R/'timing/opu_sequencer_driver.cpp'),'-CFLAGS','-O3 -std=c++20 -I'+str(R/'timing'),'-MAKEFLAGS','OPT_FAST=-O3 OPT_SLOW=-O3','-o',str(out/'opu-sequencer')]
 start=time.monotonic()
 with (out/'build.log').open('w')as log:q=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ,PATH=str(tool.parent)+os.pathsep+os.environ['PATH']))
 report={'schema':'iris.opu_sequencer_native.v1','source_identity':identity,'argv':command,'exit_status':q.returncode,'build_seconds':time.monotonic()-start,'input_sha256':{str(p):sha(p)for p in src},'source_fir_sha256':'f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4','added_edges':0,'hardware_contacted':False,'full_soc_certified':False,'timing_certified':False}
 if not q.returncode:report['native_sha256']=sha(out/'opu-sequencer')
 (out/'build.json').write_text(json.dumps(report,indent=2)+'\n');shutil.copytree(R/'timing',out/'source',ignore=shutil.ignore_patterns('*')) if False else None
 (out/'source').mkdir()
 for p in src:
  if p.parent==R/'timing':shutil.copy2(p,out/'source'/p.name)
 print(json.dumps({'exit_status':q.returncode,'source_identity':identity,'native_sha256':report.get('native_sha256'),'ports':{k:len(v)for k,v in fields.items()}}))
 if q.returncode:raise SystemExit(1)
if __name__=='__main__':main()
