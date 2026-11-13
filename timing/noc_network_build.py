#!/usr/bin/env python3
"""Build the complete mechanically extracted NoC, without an extra link edge."""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--source',type=Path,default=R/'build/noc-network-source-v1');p.add_argument('--output',type=Path,default=R/'build/noc-network-native-v1');p.add_argument('--jobs',type=int,default=6);a=p.parse_args();source=a.source.resolve();out=a.output.resolve()
 if out.exists():raise ValueError('Fresh native build output required')
 j=json.loads((source/'extraction.json').read_text());assert sha(source/'rtl/IrisNoCNetwork.sv')==j['wrapper_sha256'];fields=j['physical_ports'];inputs=[x for x in fields if x['direction']=='input'];outputs=[x for x in fields if x['direction']=='output'];out.mkdir();shutil.copytree(source/'rtl',out/'rtl');model=out/'model'
 code=(R/'timing/noc_network.cpp').read_text().split('// BEGIN GENERATED INPUT MAP')[0]+'// BEGIN GENERATED INPUT MAP\n'
 for x in inputs:
  if x['width']<64:code+='if(i.values['+str(x['index'])+']>='+str(1<<x['width'])+'ULL)throw std::invalid_argument("Physical NoC field exceeds width: '+x['name']+'");\n'
 for x in inputs:
  code+='m.'+x['port']+'=i.values['+str(x['index'])+'];\n'
 code+='m.eval();impl_->evaluated=true;\n}\nNetworkOutputs IrisNoCNetwork::sample()const{\nif(!impl_->evaluated)throw std::logic_error("Network sample requires evaluate in this edge");\nconst auto &m=*impl_->model;NetworkOutputs o{};\n'
 for x in outputs:code+='o.values['+str(x['index'])+']=m.'+x['port']+';\n'
 code+='return o;\n}\nvoid IrisNoCNetwork::commit(){\nif(!impl_->evaluated)throw std::logic_error("Network commit requires fresh evaluate");\nauto &m=*impl_->model;m.clock=1;m.eval();m.clock=0;m.eval();++impl_->edge_count;impl_->evaluated=false;\n}\nNetworkOutputs IrisNoCNetwork::step(const NetworkInputs &i){evaluate(i);auto o=sample();commit();return o;}\n'
 code+='''void IrisNoCNetwork::save(const std::filesystem::path& p)const{
 if(impl_->evaluated||!impl_->edge_count)throw std::logic_error("Network snapshot requires a committed edge boundary");
 VerilatedSave out;out.open(p.string());out<<std::uint64_t{0x495249534e455431ULL}<<std::string(IRIS_NETWORK_SOURCE_ID)<<impl_->edge_count<<*impl_->model;out.close();
}
void IrisNoCNetwork::restore(const std::filesystem::path& p){
 if(impl_->evaluated)throw std::logic_error("Network restore during pending evaluated edge");NetworkSnapshotPrefix prefix(p);
 VerilatedRestore in;in.open(p.string());std::uint64_t magic;std::string id;in>>magic>>id>>impl_->edge_count>>*impl_->model;in.close();impl_->evaluated=false;
}
std::uint64_t IrisNoCNetwork::edges()const{return impl_->edge_count;}
const char* IrisNoCNetwork::source_identity(){return IRIS_NETWORK_SOURCE_ID;}
'''
 for direction in ['input','output']:
  code+='std::span<const NetworkField> IrisNoCNetwork::'+direction+'_fields(){\nstatic constexpr NetworkField fields[]={\n'+',\n'.join('{'+json.dumps(x['name'])+','+str(x['width'])+'}'for x in fields if x['direction']==direction)+'\n};return fields;\n}\n'
 code+='}\n';(R/'timing/noc_network.cpp').write_text(code)
 tool=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator');identity=hashlib.sha256(json.dumps({'extraction_sha256':sha(source/'extraction.json'),'implementation':sha(R/'timing/noc_network.cpp'),'api_header':sha(R/'timing/noc_network.hpp'),'schema_header':sha(R/'timing/noc_network_schema.hpp'),'verilator_binary':sha(tool.with_name('verilator_bin')),'configuration':'savable/assert/port-only/O3/explicit evaluate-sample-commit/v1'},sort_keys=True).encode()).hexdigest();(R/'timing/noc_network_identity.hpp').write_text('#pragma once\n#define IRIS_NETWORK_SOURCE_ID "'+identity+'"\n')
 command=[str(tool.with_name('perl')),str(tool),'--cc','--exe','--build','-j',str(a.jobs),'--top-module','IrisNoCNetwork','--prefix','VNoCNetwork','--savable','--assert','-Wno-fatal','--x-initial','unique','--x-assign','unique','--Mdir',str(model),'-I'+str(out/'rtl'),'-y',str(out/'rtl'),'+libext+.sv+.v','+define+RANDOMIZE_MEM_INIT','+define+RANDOMIZE_REG_INIT','+define+RANDOMIZE_GARBAGE_ASSIGN','+define+RANDOMIZE_INVALID_ASSIGN',str(out/'rtl/IrisNoCNetwork.sv'),str(R/'timing/noc_network.cpp'),str(R/'timing/noc_network_driver.cpp'),'-CFLAGS','-O3 -std=c++20 -I'+str(R/'timing'),'-MAKEFLAGS','OPT_FAST=-O3 OPT_SLOW=-O3','-o',str(out/'noc-network')];(out/'command.json').write_text(json.dumps(command,indent=2)+'\n')
 with (out/'build.log').open('w')as log:q=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ,PATH=str(tool.parent)+os.pathsep+os.environ['PATH']))
 inputs=[source/'extraction.json',Path(__file__),R/'timing/noc_network.cpp',R/'timing/noc_network.hpp',R/'timing/noc_network_schema.hpp',R/'timing/noc_network_identity.hpp',R/'timing/noc_network_driver.cpp',tool,tool.with_name('verilator_bin')]
 report={'schema':'iris.complete_noc_native.v1','source_identity':identity,'argv':command,'exit_status':q.returncode,'input_sha256':{str(p):sha(p)for p in inputs},'source_sha256':{str(p):sha(p)for p in (out/'rtl').iterdir()},'evaluate_sample_commit_API':True,'added_link_edges':0,'hardware_contacted':False,'timing_certified':False}
 if not q.returncode:report['native_sha256']=sha(out/'noc-network')
 (out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'exit_status':q.returncode,'source_identity':identity,'native_sha256':report.get('native_sha256')}))
 if q.returncode:raise SystemExit(1)
if __name__=='__main__':main()
