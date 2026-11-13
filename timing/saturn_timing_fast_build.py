#!/usr/bin/env python3
"""Replace only the OPU cell FP8 numeric cone, preserving source timing state."""
import argparse,difflib,gzip,hashlib,json,os,re,shutil,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def restore(base,j,name,target):
 entry=j['files'][name];obj=base/entry['object'];assert sha(obj)==entry['object_sha256'];data=gzip.decompress(obj.read_bytes())if entry['compression']=='gzip'else obj.read_bytes();assert hashlib.sha256(data).hexdigest()==entry['sha256'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);target.chmod(entry['mode']);return {'source_manifest_key':name,'sha256':entry['sha256'],'object_sha256':entry['object_sha256']}
def specialize(original):
 # All original array state and control remain verbatim, including unreset MRF,
 # source index Pipe, full write precedence, integer datapath and io.out mux.
 header=original[:original.index('  wire [32:0]       _fma_io_out;')]
 regs=original[original.index('  reg  [31:0]       regs_0;'):original.index('  wire              f8a_rawIn_isZeroExpIn')]
 # The exact first f8 conversion starts before the rawIn wire; retain only f8macc.
 regs=regs[:regs.index('  wire [1:0]        f8a_subnormShift')]
 control=original[original.index('  reg               mrf_idx_pipe_pipe_v;'):original.index('  wire              sum_fp8_rawIn_isInf')]
 writes=original[original.index('  always @(posedge clock) begin'):original.index('  RecFNToRecFN_24 f8aw_widen')]
 tail=original[original.index('  assign io_out = _GEN[io_mrf_idx];'):]
 numeric='''  // Source FMA has two valid stages. Numeric evaluation is substituted only
  // for a real f8macc; it reads the same pre-edge MRF and preserves all source
  // register/index/write ordering. No tile initialization or idle skipping.
  import "DPI-C" pure function int unsigned iris_saturn_fp8_fma(
    input int unsigned a,b,c,fa,fb,rm);
  reg fast_valid_stage0,fast_valid_stage1;
  reg [31:0] fast_sum_stage0,sum_fp8;
  wire _fma_io_validout=fast_valid_stage1;
  always @(posedge clock) begin
    if (f8macc)
      fast_sum_stage0 <= iris_saturn_fp8_fma({24'b0,io_in_l},{24'b0,io_in_t},
        _GEN[io_mrf_idx],{31'b0,io_e5m2_l},{31'b0,io_e5m2_t},{29'b0,io_rm});
    if (fast_valid_stage0) sum_fp8 <= fast_sum_stage0;
    if (reset) begin fast_valid_stage0<=0;fast_valid_stage1<=0;end
    else begin fast_valid_stage0<=f8macc;fast_valid_stage1<=fast_valid_stage0;end
  end
'''
 result=header+regs+control+numeric+writes+tail
 assert result.count('module OuterProductCell(')==1 and 'RecFNToRecFN_24'not in result and 'MulAddRecFNPipe'not in result
 assert len(re.findall(r'reg\s+\[31:0\]\s+regs_\d+;',result))==16
 return result
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--jobs',type=int,default=8);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);frozen=R/'build/saturn-timing-component-v1-final';capsule=json.loads((frozen/'report.json').read_text());source=out/'source';source.mkdir();shutil.copy2(frozen/'build/saturn-timing-source-v1/extraction.json',source/'extraction.json');shutil.copytree(frozen/'build/saturn-timing-source-v1/compute',source/'compute');cell=source/'compute/rtl/OuterProductCell.sv';original=cell.read_text();cell.write_text(specialize(original));(out/'cell-numeric.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True),cell.read_text().splitlines(True),fromfile='saved/OuterProductCell.sv',tofile='numeric-substitution/OuterProductCell.sv')))
 for pth in(source/'compute/rtl').iterdir():
  if pth.name!='OuterProductCell.sv':assert sha(pth)==sha(frozen/'build/saturn-timing-source-v1/compute/rtl'/pth.name)
 base=R/'build/combined-frozen-35901887';j=json.loads((base/'manifest.json').read_text());numeric=out/'numeric';numeric.mkdir();restored={}
 for name in j['files']:
  if name.startswith('third_party/riscv-isa-sim-combined/softfloat/'):
   restored[name]=restore(base,j,name,numeric/'softfloat'/Path(name).name)
 for name,target in [('third_party/riscv-isa-sim-combined/riscv/iris_fp8.hpp',numeric/'iris_fp8.hpp'),('build/spike-combined/libsoftfloat.a',numeric/'libsoftfloat.a'),('build/spike-combined/config.h',numeric/'softfloat/config.h')]:restored[name]=restore(base,j,name,target)
 shutil.copy2(R/'timing/saturn_timing_fast_numeric.cpp',numeric/'saturn_timing_fast_numeric.cpp');(out/'numeric-inputs.json').write_text(json.dumps({'manifest':str(base/'manifest.json'),'manifest_sha256':sha(base/'manifest.json'),'restored':restored},indent=2)+'\n')
 native=out/'native';native.mkdir();command=[sys.executable,str(frozen/'timing/saturn_timing_build.py'),'--source',str(source/'compute'),'--output',str(native/'compute'),'--jobs',str(a.jobs)];start=time.monotonic()
 with(out/'native-build.log').open('w')as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
 sdk=out/'sdk';sdk.mkdir();sdkfiles=sdk/'sdk';sdkfiles.mkdir();local=sdk/'source';local.mkdir()
 for name in['saturn_timing.cpp','saturn_timing.hpp','saturn_timing_driver.cpp']:shutil.copy2(frozen/'build/saturn-timing-sdk-v1/source'/name,local/name)
 inputs=[Path(__file__),R/'timing/saturn_timing_fast_numeric.cpp',frozen/'report.json',base/'manifest.json',cell,native/'compute/build.json',out/'cell-numeric.patch',out/'numeric-inputs.json']+[local/x for x in['saturn_timing.cpp','saturn_timing.hpp','saturn_timing_driver.cpp']];identity=hashlib.sha256(json.dumps({str(p):sha(p)for p in inputs},sort_keys=True).encode()).hexdigest();(local/'saturn_timing_identity.hpp').write_text('#pragma once\n#define IRIS_SATURN_TIMING_SOURCE_ID "'+identity+'"\n')
 tool=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include');models=[native/'compute/model',frozen/'build/saturn-timing-native-v1/rocket/model'];common=['-O3','-std=c++20','-pthread','-I'+str(local),'-I'+str(tool),'-I'+str(tool/'vltstd'),'-I'+str(numeric),'-I'+str(numeric/'softfloat')]+['-I'+str(p)for p in models];commands=[];objects=[]
 for file in[local/'saturn_timing.cpp',numeric/'saturn_timing_fast_numeric.cpp',tool/'verilated.cpp',tool/'verilated_threads.cpp',tool/'verilated_dpi.cpp']:
  target=sdk/(file.stem+'.o');commands.append(['/usr/bin/g++',*common,'-c',str(file),'-o',str(target)]);objects.append(target)
 objects+=sorted(models[0].glob('VSaturnCompute*.o'))+sorted(models[1].glob('VSaturnRocket*.o'));soft=sdk/'softfloat-objects';soft.mkdir();subprocess.run(['/usr/bin/ar','x',str(numeric/'libsoftfloat.a')],cwd=soft,check=True);objects+=sorted(soft.glob('*.o'));lib=sdkfiles/'libiris_saturn_timing.a';commands.append(['/usr/bin/ar','rcs',str(lib),*map(str,objects)]);commands.append(['/usr/bin/g++',*common,str(local/'saturn_timing_driver.cpp'),str(lib),'-latomic','-o',str(sdk/'saturn-timing')]);commands.append(['/usr/bin/g++',*common,str(frozen/'timing/saturn_timing_bench.cpp'),str(lib),'-latomic','-o',str(sdk/'benchmark')])
 with(sdk/'build.log').open('w')as log:
  for cmd in commands:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
 shutil.copy2(local/'saturn_timing.hpp',sdkfiles/'saturn_timing.hpp');inputs +=[local/'saturn_timing_identity.hpp',tool/'verilated.cpp',tool/'verilated_threads.cpp',tool/'verilated_dpi.cpp',Path('/usr/bin/g++'),Path('/usr/bin/ar')]+list(numeric.rglob('*'));inputs=[p for p in inputs if p.is_file()];report={'schema':'iris.saturn_smallest_numeric_substitution.v1','source_identity':identity,'whole_reference_capsule_sha256':sha(frozen/'report.json'),'base_functional_native_sha256':j['binary_sha256'],'changed_RTL_modules':['OuterProductCell'],'source_control_registers_index_pipe_write_priority_retained':True,'numeric_substitution':'FP8 widening+FP32 FMA only; original integer numeric cone and all surrounding controller RTL retained','two_valid_stages_retained':True,'unreset_MRF_state_retained':True,'idle_skipping':False,'legal_rounding_modes':[0,1,2,3,4],'other_rounding_modes_fail_closed':True,'input_sha256':{str(p):sha(p)for p in inputs},'native_build_argv':command,'argv':commands,'native_sha256':sha(sdk/'saturn-timing'),'library_sha256':sha(lib),'benchmark_sha256':sha(sdk/'benchmark'),'host_seconds':time.monotonic()-start,'hardware_contacted':False,'whole_SoC_or_2percent_certified':False};(sdk/'build.json').write_text(json.dumps(report,indent=2)+'\n');(out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k]for k in['source_identity','native_sha256','library_sha256','host_seconds']}))
if __name__=='__main__':main()
