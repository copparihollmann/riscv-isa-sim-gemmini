#!/usr/bin/env python3
"""Compile typed online causal ledger and actual-source differential replay."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from saturn_timing_activity_extract import modules
R=Path(__file__).resolve().parents[1]
REF=R/'build/saturn-timing-component-v1-final'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--sdk',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();sdk=a.sdk.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);shutil.copy2(Path(__file__),out/'builder.py')
 for name in ['saturn_timing_ownership.hpp','saturn_timing_ownership.cpp','saturn_timing_ownership_replay.cpp']:shutil.copy2(R/'timing'/name,out/name)
 config_header='#pragma once\n#include <string>\n#include <vector>\nstruct SourceIterativeFU{std::string path,module;};\nstruct SourceExecutionConfig{std::string unit,sequencer;unsigned stages;std::uint64_t pipe_mask;std::vector<SourceIterativeFU> iterative;};\n'
 configurations={};source_inputs=[]
 for profile,top in [('compute','SaturnShuttleUnit'),('rocket','SaturnRocketUnit')]:
  defs=modules(REF/'build/saturn-timing-source-v1'/profile/'rtl');backend=defs[defs[top]['instances']['vu']];entries=[];rows=[]
  for unit,seq in([('vxuint','vxsint'),('vxufp','vxsfp')]if profile=='compute'else[('vxufp_int','vxsfp_int')]):
   definition=defs[backend['instances'][unit]];mask=0;iterative=[];fu_rows=[];source_inputs.append(definition['path'])
   stages=sum(1 for n in definition['declarations']if n.startswith('io_pipe_hazards_')and n.endswith('_valid'))
   for instance,module in definition['instances'].items():
    if not instance.startswith('fus_'):continue
    index=int(instance[4:]);child=defs[module];pipelined=any(re.fullmatch(r'io_pipe_\d+_valid',name)for name in child['declarations']);source_inputs.append(child['path']);fu_rows.append({'index':index,'module':module,'pipelined':pipelined,'source_path':str(child['path']),'source_sha256':sha(child['path'])})
    if pipelined:mask|=1<<index
    else:iterative.append('{'+json.dumps('vu.'+unit+'.'+instance)+','+json.dumps(module)+'}')
   entries.append('{'+json.dumps('vu.'+unit)+','+json.dumps('vu.'+seq)+','+str(stages)+','+str(mask)+'ULL,{'+','.join(iterative)+'}}');rows.append({'unit':'vu.'+unit,'sequencer':'vu.'+seq,'source_path':str(definition['path']),'source_sha256':sha(definition['path']),'pipe_hazard_stages':stages,'pipelined_FU_mask':mask,'functional_units':fu_rows})
  config_header+='inline std::vector<SourceExecutionConfig> source_'+profile+'_execution_config(){return {'+','.join(entries)+'};}\n';configurations[profile]=rows
 (out/'saturn_ownership_source_config.hpp').write_text(config_header);(out/'source-execution-config.json').write_text(json.dumps(configurations,indent=2)+'\n')
 command=['/usr/bin/g++','-O3','-std=c++20','-pthread','-I'+str(out),'-I'+str(sdk/'sdk'),str(out/'saturn_timing_ownership.cpp'),str(out/'saturn_timing_ownership_replay.cpp'),str(sdk/'sdk/libiris_saturn_timing.a'),'-latomic','-lz','-o',str(out/'replay')]
 with(out/'build.log').open('w')as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
 inputs=[Path(__file__),sdk/'build.json',sdk/'sdk/libiris_saturn_timing.a',Path('/usr/bin/g++'),out/'saturn_ownership_source_config.hpp',out/'source-execution-config.json',*source_inputs]+[out/name for name in ['saturn_timing_ownership.hpp','saturn_timing_ownership.cpp','saturn_timing_ownership_replay.cpp']];result={'schema':'iris.saturn_source_ownership_replay_build.v1','argv':command,'input_sha256':{str(p):sha(p)for p in inputs},'native_sha256':sha(out/'replay'),'only_model_physical_inputs_driven':True,'caller_node_is_metadata_only':True,'hardware_contacted':False};(out/'build.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'native_sha256':result['native_sha256']}))
if __name__=='__main__':main()
