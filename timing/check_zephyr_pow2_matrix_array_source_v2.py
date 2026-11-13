#!/usr/bin/env python3
"""NEW selected-shape witness using immutable whole source OPU objects."""
from pathlib import Path
import hashlib,json,subprocess,shutil
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 o=R/'build/zephyr-pow2-matrix-source-independent-v2';o.mkdir();p=R/'build/opu-array-rtl-proof-v2-pipelined';receipt=json.loads((p/'results.json').read_text());source=R/'hardware/opu_array/driver.cc';assert sha(source)==receipt['input_sha256'][str(source)];text=source.read_text();(o/'frozen_array_check.inc').write_text(text[:text.index('\nint main(')]+'\n');shutil.copy2(p/'port_bindings.inc',o/'port_bindings.inc');assert sha(o/'port_bindings.inc')==receipt['artifact_sha256']['port_bindings.inc']
 model=p/'model';vroot=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include');cpp=R/'timing/zephyr_pow2_matrix_array_source_v2.cpp';cmd=['g++','-O2','-std=c++20','-I'+str(o),'-I'+str(model),'-I'+str(vroot),'-I'+str(vroot/'vltstd'),str(cpp),str(model/'VOuterArray__ALL.a'),str(model/'verilated.o'),str(model/'verilated_threads.o'),'-pthread','-latomic','-o',str(o/'check')];b=subprocess.run(cmd,capture_output=True);(o/'build.stdout').write_bytes(b.stdout);(o/'build.stderr').write_bytes(b.stderr);assert b.returncode==0,b.stderr.decode()
 checks=[]
 for name,args in[('normal',[]),('wrong-golden',['--wrong-golden']),('omitted-subtile',['--omit-last-subtile'])]:
  r=subprocess.run([str(o/'check'),*args],capture_output=True,timeout=120);(o/(name+'.stdout')).write_bytes(r.stdout);(o/(name+'.stderr')).write_bytes(r.stderr);reason=b'readout mismatch'if name=='wrong-golden'else b'full-square/slot golden mismatch';checks.append(dict(name=name,exit_status=r.returncode,**{'pass':r.returncode==0 if not args else r.returncode!=0 and reason in r.stderr}))
 result=json.loads((o/'normal.stdout').read_text());report=dict(schema='iris.Zephyr_pow2_selected_shape_whole_OPU_source.v1',**{'pass':all(x['pass']for x in checks)},checks=result,controls=checks,source_scope='actual saved full16x16 OPU array and all16 MRF slots; explicit actual zeroing and output scans; source-derived32x32 subentry mapping, not Core/wholeSoC/image proof',CPU_CSR_and_sequencer_join_qualified=False,native_model_used_as_oracle=False,hardware_or_timing_labels_accessed=False,build_argv=cmd,input_sha256={str(x):sha(x)for x in[Path(__file__),cpp,source,p/'results.json',p/'port_bindings.inc',model/'VOuterArray__ALL.a',model/'verilated.o',model/'verilated_threads.o']},output_sha256={str(x):sha(x)for x in o.iterdir()if x.is_file()});(o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':report['pass'],'sha256':sha(o/'report.json')}));raise SystemExit(not report['pass'])
if __name__=='__main__':main()
