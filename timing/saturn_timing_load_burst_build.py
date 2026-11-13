#!/usr/bin/env python3
"""Synthetic legal external-D withholding at real source Rocket vector capacity."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);shutil.copy2(Path(__file__),out/'builder.py');reference=R/'build/saturn-timing-component-v1-final';model=reference/'build/saturn-timing-native-v1/rocket/model';schema=reference/'build/saturn-timing-source-v1/rocket/ports.json';j=json.loads(schema.read_text());header=out/'burst_inputs.hpp';code='static void known_inputs(VSaturnRocket&m){m.clock=0;\n'
 for f in j['words']['input']:
  if f['width']<=64:code+='m.'+f['name']+'=0;\n'
  else:
   code+='m.'+f['name']+'['+str(f['lo']//32)+']=0;\n'
   if f['word_width']>32:code+='m.'+f['name']+'['+str(f['lo']//32+1)+']=0;\n'
 xbar=reference/'build/saturn-timing-source-v1/rocket/rtl/TLXbar_i2_o1_a35d256s6k4z4u.sv';literal="assign auto_anon_out_a_bits_source = (muxState_0 ? {1'h1, auto_anon_in_0_a_bits_source} : 6'h0) | (muxState_1 ? {1'h0, auto_anon_in_1_a_bits_source} : 6'h0);";assert literal in xbar.read_text();header.write_text('#define IRIS_READER_SOURCE_BASE 32\n'+code+'}\n');source=out/'load_burst.cpp';shutil.copy2(R/'timing/saturn_timing_load_burst.cpp',source);tool=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include');lib=reference/'build/saturn-timing-sdk-v1/sdk/libiris_saturn_timing.a';command=['/usr/bin/g++','-O3','-std=c++20','-I'+str(out),'-I'+str(model),'-I'+str(tool),'-I'+str(tool/'vltstd'),str(source),str(lib),'-pthread','-latomic','-o',str(out/'load-burst')]
 with(out/'build.log').open('w')as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
 results=[]
 for lmul in[2,3]:
  for seed in[0,17]:
   cmd=[str(out/'load-burst'),str(lmul),str(seed)];q=subprocess.run(cmd,capture_output=True,text=True,timeout=30);label='m'+str(1<<lmul)+'-seed'+str(seed);(out/(label+'.stdout')).write_text(q.stdout);(out/(label+'.stderr')).write_text(q.stderr)
   if q.returncode:raise ValueError('Bounded source load burst failed '+label+' '+q.stderr)
   result=next(json.loads(x.split(' ',1)[1])for x in q.stdout.splitlines()if x.startswith('BURST_RESULT '));results.append({'argv':cmd,**result})
 core=reference/'build/saturn-timing-reference-v1/rtl/Rocket.sv';gate='id_csr_en & _csr_io_decode_0_vector_csr & id_vec_busy';assert gate in core.read_text();inputs=[Path(__file__),R/'timing/saturn_timing_load_burst.cpp',source,header,schema,xbar,core,model/'VSaturnRocket.h',model/'VSaturnRocket___024root.h',lib,reference/'report.json',tool/'verilated.h',tool/'verilated.cpp',Path('/usr/bin/g++')];report={'schema':'iris.saturn_rocket_restore_burst_probe.v1','pass':True,'results':results,'argv':command,'input_sha256':{str(p):sha(p)for p in inputs},'native_sha256':sha(out/'load-burst'),'external_reader_source_range':[32,63],'reader_source_map_citation':{'path':str(xbar),'sha256':sha(xbar),'literal':literal},'core_CSR_gate_citation':{'path':str(core),'sha256':sha(core),'literal':gate},'external_service_fixture':'ATL Aready1, identity one-cycle TLB, all D withheld until four source loads retire at requested peak;512 further core edges with noD; then matching ordered4x64b D beats/32B request, held until accepted. Explicit synthetic boundary, no physical latency assumption.','internal_state_or_readiness_injected':False,'model_objects_or_source_RTL_modified':False,'full_Rocket_core_CSR_instruction_executed':False,'CSR_gate_scope':'Actual unit backend_busy/trap_check_busy and source-audited RocketCore vector-CSR stall predicate; no scalar instruction is sent as a vector command.','physical_FPGA_fault_or_cause_identified':False,'hardware_contacted':False};report['artifact_sha256']={str(p.relative_to(out)):sha(p)for p in out.rglob('*')if p.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'results':results,'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
