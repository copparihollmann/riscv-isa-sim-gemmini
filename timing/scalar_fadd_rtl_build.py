#!/usr/bin/env python3
"""Extract exact small saved FPU subtrees; add a read-only control wrapper."""
import argparse,hashlib,json,re,shutil,subprocess,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);src=ROOT/'build/rtl-verilator/gen-collateral';manifest=json.loads((ROOT/'build/rtl-verilator/manifest.json').read_text());modules={}
 for f in src.glob('*.sv'):
  text=f.read_text();m=re.search(r'^module\s+(\w+)\s*\(',text,re.M)
  if m:modules[m[1]]=f
 names=set();todo=['ShuttleFPPipe','FPU']
 while todo:
  name=todo.pop()
  if name in names:continue
  if name not in modules:raise ValueError('Unresolved exact module '+name)
  names.add(name);text=modules[name].read_text()
  todo += [m for m in re.findall(r'^\s*(\w+)\s+(?:#\s*\([^;]*?\)\s*)?\w+\s*\(',text,re.M) if m in modules and m not in names]
 rtl=out/'rtl';rtl.mkdir();inputs={};files=[]
 for name in sorted(names):
  f=modules[name];expected=manifest['sim_source_sha256'][str(f)];assert sha(f)==expected;shutil.copyfile(f,rtl/f.name);inputs[str(f)]=expected;files.append(str(rtl/f.name))
 def ports(module):
  text=modules[module].read_text().split('module '+module+'(',1)[1].split(');',1)[0]
  return re.findall(r'^\s*(input|output)\s*(\[[^\]]+\])?\s*(\w+)\s*[,\t ]',text,re.M)
 sh={'clock':'clock','reset':'reset','io_in_valid':'sh_valid','io_in_bits_inst':'{20\'b0,sh_rd,7\'h53}','io_in_bits_fp_ctrl_ren2':"1'b1",'io_in_bits_fp_ctrl_swap23':"1'b1",'io_in_bits_fp_ctrl_typeTagIn':'sh_tag','io_in_bits_fp_ctrl_typeTagOut':'sh_tag','io_in_bits_fp_ctrl_fma':"1'b1",'io_in_bits_fp_ctrl_wflags':"1'b1",'io_s1_kill':'sh_k1','io_s2_kill':'sh_k2','io_out_valid':'sh_out_valid','io_out_rd':'sh_out_rd','io_out_tag':'sh_out_tag'}
 ro={'clock':'clock','reset':'reset','io_valid':'ro_valid','io_inst':'ro_inst','io_killx':'ro_kx','io_killm':'ro_km','io_fcsr_flags_valid':'ro_flags_valid','io_fcsr_rdy':'ro_ready','io_nack_mem':'ro_nack','io_ll_resp_val':'ro_load','io_ll_resp_tag':'ro_load_rd','io_ll_resp_type':"3'd3"}
 wrapper='''module IrisScalarFaddControlReference(input clock,reset,sh_valid,sh_k1,sh_k2,input[4:0]sh_rd,input[1:0]sh_tag,input ro_valid,ro_kx,ro_km,ro_load,input[4:0]ro_load_rd,input[31:0]ro_inst,output sh_out_valid,output[4:0]sh_out_rd,output[1:0]sh_out_tag,output ro_flags_valid,ro_ready,ro_nack,ro_rf_write,output[4:0]ro_rf_rd);\n'''
 for module,instance,mapping in [('ShuttleFPPipe','sh',sh),('FPU','ro',ro)]:
  ps=ports(module);require_names=set(mapping)-{name for _,_,name in ps};assert not require_names,require_names
  wrapper+=module+' '+instance+'(\n'+',\n'.join('.'+name+'('+mapping.get(name,"'0"if direction=='input'else'')+')'for direction,width,name in ps)+'\n);\n'
 wrapper+='assign ro_rf_write=ro.wen[0] & ~ro.wbInfo_0_cp;\nassign ro_rf_rd=ro.wbInfo_0_rd;\nendmodule\n';w=rtl/'IrisScalarFaddControlReference.sv';w.write_text(wrapper);files.append(str(w));(out/'files.f').write_text('\n'.join(files)+'\n')
 v=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator');argv=[str(v),'--cc','--build','--exe','-j','16','--top-module','IrisScalarFaddControlReference','--Mdir',str(out/'obj'),'-Wno-fatal','--assert','--x-assign','unique','--x-initial','unique','-CFLAGS','-std=c++20 -O2','-f',str(out/'files.f'),str(ROOT/'timing/scalar_fadd_rtl_check.cpp')]
 (out/'argv.json').write_text(json.dumps(argv,indent=2)+'\n')
 with(out/'build.log').open('w')as f:done=subprocess.run(argv,stdout=f,stderr=subprocess.STDOUT,env=dict(os.environ,PATH="/scratch/eygao/iris-cy/.conda-env/bin:"+os.environ["PATH"]))
 report=dict(schema='iris.scalar_fadd_saved_RTL_control_build.v1',status='built'if done.returncode==0 else'failed',exit_status=done.returncode,module_count=len(names),input_sha256=inputs,source_FIR_sha256=manifest['source_fir_sha256'],wrapper_sha256=sha(w),all_target_RTL_bytes_unchanged=True,internal_control_outputs_read_only=True,host_driver_sha256=sha(ROOT/'timing/scalar_fadd_rtl_check.cpp'),verilator_sha256=sha(v.resolve()),argv=argv,hardware_contacted=False)
 (out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'exit_status':done.returncode,'modules':len(names)}));raise SystemExit(done.returncode)
if __name__=='__main__':main()
