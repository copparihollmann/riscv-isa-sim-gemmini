#!/usr/bin/env python3
"""Offline source-frontend diagnostic; never a simulator calibration or fast path."""
import argparse,hashlib,json,os,pathlib,subprocess,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
 component=ROOT/'build/frontend-rtl-peer-component-v2';obj=component/'obj';inc=pathlib.Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include');cxx=pathlib.Path('/usr/bin/g++').resolve()
 common=['-std=c++20','-O2','-I'+str(ROOT/'pipeline'),'-I'+str(ROOT/'timing'),'-I'+str(component),'-I'+str(obj),'-I'+str(inc),'-I'+str(inc/'vltstd')]
 tail=[str(ROOT/'timing/shuttle_issue.cpp'),str(obj/'VShuttleFrontend__ALL.a'),str(obj/'verilated.o'),str(obj/'verilated_threads.o'),'-pthread']
 commands=[];inputs=[pathlib.Path(__file__).resolve(),ROOT/'pipeline/frontend_alignment_oracle.cpp',ROOT/'pipeline/frontend_alignment_peer.cpp',ROOT/'pipeline/frontend_rtl_peer_context.cpp',ROOT/'pipeline/frontend_rtl_peer.hpp',ROOT/'pipeline/frontend_branch.hpp',ROOT/'timing/shuttle_issue.hpp',ROOT/'timing/shuttle_issue.cpp',ROOT/'timing/shuttle_decode_rows.inc',component/'results.json',component/'zero_inputs.inc',obj/'VShuttleFrontend__ALL.a',obj/'verilated.o',obj/'verilated_threads.o',obj/'VShuttleFrontend___024root.h',cxx]
 before={str(x):sha(x)for x in inputs}
 for name,wrapper in [('plain','frontend_rtl_peer_context.cpp'),('observed','frontend_alignment_peer.cpp')]:
  argv=[str(cxx),*common,str(ROOT/'pipeline/frontend_alignment_oracle.cpp'),str(ROOT/'pipeline'/wrapper),*tail,'-o',str(out/name)];commands.append(argv);r=subprocess.run(argv,capture_output=True);(out/(name+'.build.stdout')).write_bytes(r.stdout);(out/(name+'.build.stderr')).write_bytes(r.stderr);assert r.returncode==0
 cases=[(pc,256,seed)for pc in [0x80000468,0x80000712]for seed in [1,17,31]]+[(0x80000440+offset,64,1)for offset in range(0,64,2)];results=[]
 for index,(pc,n,seed)in enumerate(cases):
  row={'loop_pc':pc,'n':n,'seed':seed};captures={}
  for name in ['plain','observed']:
   argv=[str(out/name),hex(pc),str(n),str(seed)];env=dict(os.environ);env.pop('IRIS_ALIGNMENT_DEBUG',None)
   if name=='observed':env['IRIS_ALIGNMENT_DEBUG']='1'
   t=time.monotonic();r=subprocess.run(argv,env=env,capture_output=True,timeout=30);assert r.returncode==0,(argv,r.stderr)
   prefix=out/(f'{index:03d}-'+name);prefix.with_suffix('.stdout').write_bytes(r.stdout);prefix.with_suffix('.stderr').write_bytes(r.stderr);captures[name]=r.stdout
   if name=='plain':row.update(json.loads(r.stdout));row['plain_seconds']=time.monotonic()-t
   else:row['duplicate_btb_clear_edges']=r.stderr.count(b'BTB_DUPLICATE_BEFORE');assert row['duplicate_btb_clear_edges']==r.stderr.count(b'BTB_DUPLICATE_AFTER')
  assert captures['plain']==captures['observed'];row['observer_output_byteidentical']=True;results.append(row)
 assert all(sha(x)==digest for x,digest in before.items())
 report=dict(schema='iris.frontend.alignment_source_oracle.v1',**{'pass':True},commands=commands,input_sha256=before,binary_sha256={name:sha(out/name)for name in ['plain','observed']},results=results,scope='actual saved-ShuttleFrontend; source select_rrd finite literal ALU/ADDIW/BNE loop; branchMEM atRRD+2; no older-register hazards for this finite stimulus; wrongpath held by legal consumer backpressure; synthetic IcachefirstD3/gap1; actual1024post-resetidleedges let512-entryBHTclear complete; notwholeCPU/FPGAassociation/calibration',source_state_injected=False,rtl_objects_changed=False,fast_native_integration=False,timing_certified=False)
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'cases':len(results)}))
if __name__=='__main__':main()
