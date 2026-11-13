#!/usr/bin/env python3
"""Compile the unchanged saved ShuttleCore for independent LSU phase evidence."""
import argparse,hashlib,json,os,re,shutil,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];V=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator');SRC=R/'build/rtl-verilator/gen-collateral'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--jobs',type=int,default=6);a=p.parse_args();out=a.output.resolve()
 if out.exists():raise ValueError('fresh phase proof build required')
 modules={}
 for q in SRC.iterdir():
  if q.suffix in ['.sv','.v']:
   for n in re.findall(r'^module\s+(\w+)',q.read_text(),re.M):modules[n]=q
 selected={};todo=['ShuttleCore']
 while todo:
  n=todo.pop()
  if n in selected:continue
  q=modules[n];selected[n]=q;s=q.read_text();children=set(re.findall(r'^\s*(\w+)\s+\w+\s*\(',s,re.M));children.update(re.findall(r'^\s*(\w+)\s*#\([\s\S]*?\)\s+\w+\s*\(',s,re.M));todo.extend(children&modules.keys()-selected.keys())
 out.mkdir();(out/'rtl').mkdir()
 for q in set(selected.values()):shutil.copy2(q,out/'rtl'/q.name)
 top=(out/'rtl/ShuttleCore.sv').read_text();head=top[:top.index('\n);')];fields=[{'name':n,'width':int(w)+1 if w else 1,'direction':d}for d,w,n in re.findall(r'^\s*(input|output)\s+(?:\[(\d+):0\]\s+)?(\w+)',head,re.M)];(out/'ports.json').write_text(json.dumps(fields,indent=2)+'\n')
 init='\n'.join('m.'+f['name']+'=0;'for f in fields if f['direction']=='input');(out/'initialize.hpp').write_text(init+'\n');env=dict(os.environ,PATH=str(V.parent)+':'+os.environ['PATH']);cmd=[str(V.with_name('perl')),str(V),'--cc','--build','-j',str(a.jobs),'--top-module','ShuttleCore','--prefix','VShuttleLSUPhase','--assert','-Wno-fatal','--x-initial','unique','--x-assign','unique','--Mdir',str(out/'obj'),'-I'+str(out/'rtl'),'-y',str(out/'rtl'),'+libext+.sv+.v','+define+RANDOMIZE_MEM_INIT','+define+RANDOMIZE_REG_INIT',str(out/'rtl/ShuttleCore.sv'),'-MAKEFLAGS','CXX=/usr/bin/g++ LINK=/usr/bin/g++ AR=/usr/bin/ar RANLIB=/usr/bin/ranlib OPT_FAST=-O3 OPT_SLOW=-O3'];start=time.monotonic()
 with(out/'build.stdout').open('w')as stdout,(out/'build.stderr').open('w')as stderr:status=subprocess.run(cmd,env=env,stdout=stdout,stderr=stderr).returncode
 result={'schema':'iris.source_ShuttleCore_LSU_phase_build.v1','exit_status':status,'argv':[cmd],'source_module_count':len(selected),'source_sha256':{str(q):sha(q)for q in sorted(set(selected.values()))},'input_sha256':{str(q):sha(q)for q in [Path(__file__),V,V.with_name('verilator_bin'),V.with_name('perl'),Path('/usr/bin/g++')]},'host_seconds':time.monotonic()-start,'no_internal_state_or_ready_replay':True,'hardware_contacted':False,'source_image_association_verified':False}
 (out/'build.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'exit_status':status,'modules':len(selected),'host_seconds':result['host_seconds']}));raise SystemExit(status)
if __name__=='__main__':main()
