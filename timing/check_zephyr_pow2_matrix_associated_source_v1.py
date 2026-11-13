#!/usr/bin/env python3
"""Verbatim associated c0f OPU closure, explicit physical-port matrix oracle."""
from pathlib import Path
import hashlib,json,re,subprocess,os,shutil
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 o=R/'build/zephyr-pow2-matrix-associated-source-v1';o.mkdir();meta=R/'build/firesim-observability-archived-driver-v3/report.json';m=json.loads(meta.read_text());source=Path(next(k for k in m['input_sha256']if k.endswith('/design/FireSim-generated.sv')));assert sha(source)==m['input_sha256'][str(source)]=='c0f972d2a63be8170f7c84a38633fbede855f00d3022e81141fa0bb274397b64';text=source.read_text();blocks={x.group(1):x.group()for x in re.finditer(r'(?ms)^module\s+(\w+)\b.*?^endmodule',text)};todo=['OuterProductUnit'];closure=set()
 while todo:
  n=todo.pop()
  if n in closure:continue
  closure.add(n);body=re.sub(r'//[^\n]*','',blocks[n]);todo.extend({a for a,b in re.findall(r'(?m)^\s*(\w+)\s+(\w+)\s*\(',body)if a in blocks}-closure)
 assert len(closure)==11
 rtl=o/'rtl';rtl.mkdir();paths=[]
 for n in sorted(closure):p=rtl/(n+'.sv');p.write_text(blocks[n]+'\n');paths.append(p)
 old=R/'build/opu-array-rtl-proof-v2-pipelined';receipt=json.loads((old/'results.json').read_text());driver=R/'hardware/opu_array/driver.cc';assert sha(driver)==receipt['input_sha256'][str(driver)];body=driver.read_text();(o/'frozen_array_check.inc').write_text(body[:body.index('\nint main(')]+'\n');shutil.copy2(old/'port_bindings.inc',o/'port_bindings.inc')
 declared=set(re.findall(r'input\s+(?:\[[^\]]+\]\s+)?(io_op_\w+)',blocks['OuterProductUnit']));previous=set(re.findall(r'input\s+(?:\[[^\]]+\]\s+)?(io_op_\w+)',(R/'build/rtl-verilator/gen-collateral/OuterProductUnit.sv').read_text()));assert declared==previous and len(declared)==105
 tools=Path('/scratch/eygao/iris-cy/.conda-env');model=o/'model';cpp=R/'timing/zephyr_pow2_matrix_array_source_v2.cpp';cmd=[str(tools/'bin/perl'),str(tools/'bin/verilator'),'--cc','--exe','--build','-j','8','--top-module','OuterProductUnit','--prefix','VOuterArray','-O3','-Wno-fatal','--Mdir',str(model),'-CFLAGS','-std=c++20 -I'+str(o),'-MAKEFLAGS','CXX=/usr/bin/g++ LINK=/usr/bin/g++ AR=ar RANLIB=ranlib',*[str(p)for p in paths],str(cpp)]
 with(o/'build.log').open('wb')as so:rc=subprocess.run(cmd,stdout=so,stderr=subprocess.STDOUT,env=dict(os.environ,VERILATOR_ROOT=str(tools/'share/verilator')),timeout=600).returncode
 assert rc==0,'associated source build failed'
 checks=[]
 for name,args,reason in[('normal',[],b''),('wrong-golden',['--wrong-golden'],b'readout mismatch'),('omitted-subtile',['--omit-last-subtile'],b'full-square/slot golden mismatch')]:
  r=subprocess.run([str(model/'VOuterArray'),*args],capture_output=True,timeout=120);(o/(name+'.stdout')).write_bytes(r.stdout);(o/(name+'.stderr')).write_bytes(r.stderr);checks.append(dict(name=name,exit_status=r.returncode,**{'pass':r.returncode==0 if not args else r.returncode!=0 and reason in r.stderr}))
 report=dict(schema='iris.Zephyr_pow2_associated_whole_OPU_source.v1',**{'pass':all(x['pass']for x in checks)},checks=json.loads((o/'normal.stdout').read_text()),controls=checks,associated_source_sha256=sha(source),verbatim_module_sha256={p.stem:sha(p)for p in paths},actual_source_inputs_only=True,source_registers_initialized_by_actual_zero=True,CPU_sequencer_and_full_image_equivalence_claim=False,hardware_or_timing_labels_accessed=False,build_argv=cmd,input_sha256={str(p):sha(p)for p in[Path(__file__),source,meta,driver,cpp,old/'results.json',old/'port_bindings.inc']},output_sha256={str(p):sha(p)for p in o.iterdir()if p.is_file()});(o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':report['pass'],'sha256':sha(o/'report.json')}));raise SystemExit(not report['pass'])
if __name__=='__main__':main()
