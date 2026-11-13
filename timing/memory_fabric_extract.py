#!/usr/bin/env python3
"""Extract exact saved tile CDC/width and L2 manager adaptor cuts, adding no state."""
import argparse,collections,hashlib,json,re,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CAP=ROOT/'build/rtl-memory-return-path-v1-final'
SRC=CAP/'build/rtl-verilator/gen-collateral'
PIN='2e32a62c428c8f434c7893beb419da576b1e3a7ff4f4574aef41dc2c1f1dac0c'
CUTS={
 'rocket_tile':('RocketTile',('tlMasterXbar','widget'),'IrisRocketTileAdapters','rocket'),
 'rocket_source':('TilePRCIDomain_2',('asource',),'IrisRocketClockSource','rocket'),
 'rocket_sink':('DigitalTop',('sbus_coupler_from_rockettile',),'IrisRocketClockSink','uncore'),
 'manager':('CoherenceManagerWrapper',('InclusiveCache_inner_TLBuffer','InclusiveCache_outer_TLBuffer','cork','l2_ctrl_xing','binder'),'IrisCoherenceAdapters','uncore'),
}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ports(text):
 m=re.search(r'^module\s+(\w+)\(',text,re.M);assert m
 stop=text.index('\n);',m.end());out={}
 for direction,width,name in re.findall(r'^\s*(input|output)\s+(?:\[(\d+:\d+)\]\s+)?(\w+)',text[m.end():stop],re.M):
  assert not width or int(width.split(':')[1])==0
  out[name]={'direction':direction,'width':int(width.split(':')[0])+1 if width else 1}
 return out

def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=ROOT/'build/memory-fabric-adapters-source-v1');a=p.parse_args();out=a.output.resolve()
 if out.exists():raise ValueError('fresh extraction output required')
 assert sha(CAP/'report.json')==PIN
 modules={}
 for directory in (SRC,ROOT/'build/rtl-verilator/gen-collateral'):
  for q in directory.iterdir():
   if q.suffix in ('.sv','.v'):
    for name in re.findall(r'^module\s+(\w+)',q.read_text(),re.M):modules.setdefault(name,q)
 sources={};cuts={};wrappers={}
 for kind,(parent,chosen,top,domain)in CUTS.items():
  path=modules[parent];text=path.read_text();parent_ports=ports(text)
  decls={n:int(w.split(':')[0])+1 if w else 1 for w,n in re.findall(r'^\s*(?:input|output|wire|reg)\s+(?:\[(\d+:\d+)\]\s+)?(\w+)',text,re.M)}
  selected=[];allnets=set();produced={};consumed=collections.defaultdict(list);external_consumed=set();clocknets=set();resetnets=set()
  for m in re.finditer(r'^  (\w+) (\w+) \(',text,re.M):
   end=text.find('\n  );',m.end());assert end>0
   block=text[m.start():end+6];info=ports(modules[m[1]].read_text());connections={}
   for line in block.splitlines()[1:]:
    line=line.split('//')[0].strip();c=re.fullmatch(r'\.(\w+)\s*\((.*)\),?',line)
    if not c:continue
    port,expression=c.groups();assert port in info,(parent,m[2],port)
    connections[port]={'expression':expression,**info[port]}
    if m[2]not in chosen:
     if info[port]['direction']=='input':external_consumed.update(re.findall(r'\b[A-Za-z_]\w*\b',expression))
     continue
    value=re.fullmatch(r'([A-Za-z_]\w*)(?:\[(\d+):(\d+)\])?',expression)
    if not value:raise ValueError('compound selected expression requires an explicit source-preserving lowering: '+str((parent,m[2],port,expression)))
    net,hi,lo=value.groups();assert net in decls
    assert (int(hi)-int(lo)+1 if hi else decls[net])==info[port]['width'],(parent,m[2],port,expression)
    if hi:assert info[port]['direction']=='input'and int(hi)<decls[net]and int(lo)<=int(hi)
    allnets.add(net)
    if port=='clock'or port.endswith('_clock'):clocknets.add(net)
    if port=='reset'or port.endswith('_reset'):resetnets.add(net)
    if info[port]['direction']=='output':
     assert net not in produced;produced[net]=(m[2],port)
    else:consumed[net].append((m[2],port))
   if m[2]in chosen:
    assert connections.keys()==info.keys(),(parent,m[2],info.keys()-connections.keys())
    selected.append({'module':m[1],'name':m[2],'source_start_line':text[:m.start()].count('\n')+1,'connections':connections,'source_block':block})
  assert len(selected)==len(chosen) and len(clocknets)==len(resetnets)==1,(kind,len(selected),clocknets,resetnets)
  for assignment in re.finditer(r'^\s*assign\s+\w+\s*=\s*([^;]+);',text,re.M):external_consumed.update(re.findall(r'\b[A-Za-z_]\w*\b',assignment[1]))
  inputs=sorted(allnets-produced.keys()-clocknets)
  outputs=sorted(n for n in produced if n not in consumed or n in external_consumed or parent_ports.get(n,{}).get('direction')=='output')
  schema=[]
  for direction,names in [('input',inputs),('output',outputs)]:
   for idx,name in enumerate(names):schema.append({'name':name,'direction':direction,'index':idx,'port':('i_'if direction=='input'else'o_')+str(idx),'width':decls[name],'producer':produced.get(name),'consumers':consumed.get(name,[]),'reset':name in resetnets})
  assert max(x['width']for x in schema)<=256
  wrapper='// Mechanical saved-source connectivity; no added state or clock edge.\nmodule '+top+'(\n  input edge_clock,\n'+',\n'.join('  '+x['direction']+' '+('['+str(x['width']-1)+':0] 'if x['width']>1 else'')+x['port']for x in schema)+'\n);\n'
  wrapper+=''.join('  wire '+('['+str(decls[n]-1)+':0] 'if decls[n]>1 else'')+n+';\n'for n in sorted(allnets))
  wrapper+='  assign '+next(iter(clocknets))+' = edge_clock;\n'
  for x in schema:wrapper+='  assign '+(x['name']+' = '+x['port']if x['direction']=='input'else x['port']+' = '+x['name'])+';\n'
  wrapper+='\n'.join(x['source_block']for x in selected)+'\nendmodule\n';wrappers[top]=wrapper
  closure={};pending=[x['module']for x in selected]
  while pending:
   mod=pending.pop()
   if mod in closure:continue
   file=modules[mod];closure[mod]=file;sources[str(file)]=sha(file)
   children=set(re.findall(r'^\s*(\w+)\s+\w+\s*\(',file.read_text(),re.M));children.update(re.findall(r'^\s*(\w+)\s*#\([\s\S]*?^\s*\)\s*\w+\s*\(',file.read_text(),re.M));pending.extend(children&modules.keys()-closure.keys())
  cuts[kind]={'parent':parent,'parent_source':str(path),'parent_sha256':sha(path),'selected_instances':selected,'top':top,'clock_domain':domain,'source_clock_net':next(iter(clocknets)),'source_reset_net':next(iter(resetnets)),'physical_ports':schema,'modules':sorted(closure),'input_count':len(inputs),'output_count':len(outputs),'wrapper_sha256':hashlib.sha256(wrapper.encode()).hexdigest()}
 out.mkdir();(out/'rtl').mkdir()
 for name,digest in sources.items():
  q=Path(name);shutil.copyfile(q,out/'rtl'/q.name);assert sha(out/'rtl'/q.name)==digest
 for top,wrapper in wrappers.items():(out/'rtl'/(top+'.sv')).write_text(wrapper)
 result={'schema':'iris.memory_fabric_adapters_source.v1','source_capsule':str(CAP/'report.json'),'source_capsule_sha256':PIN,'source_fir_sha256':json.loads((CAP/'report.json').read_text())['source_fir_sha256'],'cuts':cuts,'source_files':sources,'extracted_files':{p.name:sha(p)for p in sorted((out/'rtl').iterdir())},'extractor_sha256':sha(__file__),'RTL_logic_changed':False,'added_clock_edges':0,'external_service_inferred':False,'hardware_contacted':False,'timing_certified':False,'deployed_image_association_verified':False}
 (out/'extraction.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'cuts':{k:{'inputs':x['input_count'],'outputs':x['output_count'],'modules':len(x['modules'])}for k,x in cuts.items()},'report_sha256':sha(out/'extraction.json')}))
if __name__=='__main__':main()
