#!/usr/bin/env python3
"""Extract exact configured Saturn runtime units and physical scalar/memory ports."""
import argparse,hashlib,json,re,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[1];CAP=R/'build/opu-sequencer-component-v2-final';SRC=CAP/'build/opu-sequencer-reference-v1/rtl'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ports(path,module):
 s=path.read_text().split('module '+module+'(',1)[1].split('\n);',1)[0];s='\n'.join(x.split('//')[0]for x in s.splitlines());ps=[]
 for direction,msb,name in re.findall(r'\b(input|output)\s+(?:\[(\d+):0\]\s+)?(\w+)\s*[,\n]',s+'\n'):
  ps.append({'direction':direction,'width':int(msb)+1 if msb else 1,'name':name})
 assert len(ps)==len(re.findall(r'\b(?:input|output)\b',s)),('Port parse incomplete',module)
 return ps

def closure(module,files):
 pending=[module];result={}
 while pending:
  name=pending.pop()
  if name in result:continue
  path=files[name];result[name]=path;s=path.read_text();children=set(re.findall(r'^\s*(\w+)\s+\w+\s*\(',s,re.M));children.update(re.findall(r'^\s*(\w+)\s*#\([\s\S]*?^\s*\)\s*\w+\s*\(',s,re.M))
  pending.extend(child for child in children if child in files)
 return result

def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);assert sha(CAP/'report.json')=='389c3b0660c161f0a753ca8e27dc586ab8c8eae7010b5434689eec17e6c866ca';manifest=json.loads((CAP/'build/rtl-verilator/manifest.json').read_text());expected={Path(k).name:v for k,v in manifest['sim_source_sha256'].items()};files={}
 for path in SRC.iterdir():
  if path.suffix not in ['.v','.sv']:continue
  m=re.search(r'^module\s+(\w+)',path.read_text(),re.M)
  if m:files[m[1]]=path
 profiles={}
 for profile,module,harts,dlen,backend in [('compute','SaturnShuttleUnit',[0,1],128,'VectorBackend'),('rocket','SaturnRocketUnit',[2],256,'VectorBackend_2')]:
  paths=closure(module,files);directory=out/profile;directory.mkdir();rtl=directory/'rtl';rtl.mkdir()
  for name,path in paths.items():
   assert sha(path)==expected[path.name],('Changed saved source',path);shutil.copy2(path,rtl/path.name)
  physical=ports(files[module],module);words={}
  for direction in ['input','output']:
   fs=[]
   for f in physical:
    if f['direction']!=direction or f['name']=='clock':continue
    for lo in range(0,f['width'],64):fs.append({**f,'word_index':len(fs),'lo':lo,'word_width':min(64,f['width']-lo),'word_name':f['name']+('_'+str(lo//64)if f['width']>64 else'')})
   words[direction]=fs
  info={'profile':profile,'top_module':module,'source_harts':harts,'VLEN_bits':256,'DLEN_bits':dlen,'ELEN_bits':64,'OPU':profile=='compute','physical_ports':physical,'words':words,'source_files':{str(path):sha(path)for path in paths.values()},'modules':len(paths),'backend_module':backend,'clock_IDs':{str(h):'sbusFixedClockNode.out'+str(h+2)if h<2 else'tileClockGroup.rockettile_2'for h in harts},'clock_period_not_assumed_by_API':True,'source_fir_sha256':manifest['source_fir_sha256'],'all_runtime_queues_and_VRF_internal':True,'actual_scalar_EX_MEM_COM_interface':True,'memory_boundary':'compute ATL256; Rocket ATL64 + Hella256. Actual TLB/sharedFPU ports remain external. Width widgets, tile-level arbiter/CDC outside unit remain external.','functional_definedness':'Unreset VRF/tile state requires explicit source-valid initialization or an independently proven architectural knownness contract; two-state numeric payload is not a definedness proof.','hardware_contacted':False};(directory/'ports.json').write_text(json.dumps(info,indent=2)+'\n');profiles[profile]={'schema':str(directory/'ports.json'),'schema_sha256':sha(directory/'ports.json'),'module':module,'modules':len(paths),'physical_ports':len(physical),'input_words':len(words['input']),'output_words':len(words['output'])}
 report={'schema':'iris.saturn_runtime_source_cuts.v1','profiles':profiles,'source_capsule_sha256':sha(CAP/'report.json'),'source_fir_sha256':manifest['source_fir_sha256'],'source_repositories':json.loads((CAP/'hardware/manifest.json').read_text())['repositories'],'extractor_sha256':sha(__file__),'source_checkout_or_Ethan_image_association':False,'production_performance_architecture':False,'whole_SoC_timing_certified':False,'hardware_contacted':False};(out/'extraction.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(profiles))
if __name__=='__main__':main()
