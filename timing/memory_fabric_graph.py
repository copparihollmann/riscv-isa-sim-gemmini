#!/usr/bin/env python3
"""Join frozen cache/NoC and new adaptor pins by original saved hierarchy nets."""
import argparse,collections,hashlib,json,re
from pathlib import Path
R=Path(__file__).resolve().parents[1]
SRC=R/'build/rtl-memory-return-path-v1-final/build/rtl-verilator/gen-collateral'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ports(text):
 m=re.search(r'^module\s+(\w+)\(',text,re.M);assert m;end=text.index('\n);',m.end())
 return {n:{'direction':d,'width':int(w.split(':')[0])+1 if w else 1}for d,w,n in re.findall(r'^\s*(input|output)\s+(?:\[(\d+:\d+)\]\s+)?(\w+)',text[m.end():end],re.M)}
class Hierarchy:
 def __init__(self):self.modules={};self.paths={'':('DigitalTop',None)};self.used=set()
 def load(self,mod):
  if mod in self.modules:return self.modules[mod]
  p=SRC/(mod+'.sv');self.used.add(p);t=p.read_text();instances={}
  for m in re.finditer(r'^  (\w+) (\w+) \(',t,re.M):
   end=t.find('\n  );',m.end());assert end>0;b=t[m.start():end+6]
   connections={}
   for line in b.splitlines()[1:]:
    c=re.fullmatch(r'\s*\.(\w+)\s*\((.*)\),?\s*',line.split('//')[0])
    if c:connections[c[1]]=c[2]
   instances[m[2]]={'module':m[1],'connections':connections,'source_start_line':t[:m.start()].count('\n')+1}
  decls={n:int(w.split(':')[0])+1 if w else 1 for w,n in re.findall(r'^\s*(?:input|output|wire|reg)\s+(?:\[(\d+:\d+)\]\s+)?(\w+)',t,re.M)}
  aliases={n:e.strip()for n,e in re.findall(r'^\s*assign\s+(\w+)\s*=\s*([^;]+);',t,re.M)}
  x={'ports':ports(t),'instances':instances,'decls':decls,'aliases':aliases,'path':str(p)};self.modules[mod]=x;return x
 def at(self,path):
  if path in self.paths:return self.load(self.paths[path][0])
  parent,sep,name=path.rpartition('/');info=self.at(parent);inst=info['instances'][name];self.paths[path]=(inst['module'],inst);return self.load(inst['module'])
 def resolve(self,path,expression,trail=()):
  key=(path,expression)
  if key in trail:raise ValueError('source alias cycle '+str(trail))
  t=self.at(path);value=re.fullmatch(r'([A-Za-z_]\w*)(?:\[(\d+):(\d+)\])?',expression)
  if value:
   n,hi,lo=value.groups();assert n in t['decls'],(path,n)
   if n in t['ports']and path:
    parent,sep,child=path.rpartition('/');expr=self.paths[path][1]['connections'][n];out=self.resolve(parent,expr,trail+(key,))
   elif n in t['aliases']:
    # Resolve only transparent source aliases. Logic expressions stay explicit,
    # never silently replaced by an observed state or a guessed constant.
    out=self.resolve(path,t['aliases'][n],trail+(key,))
   else:out={'op':'net','name':('DigitalTop/'+path+'/'if path else'DigitalTop/')+n,'width':t['decls'][n]}
   if hi:
    hi=int(hi);lo=int(lo);assert 0<=lo<=hi<out['width'];out={'op':'slice','value':out,'high':hi,'low':lo,'width':hi-lo+1}
   return out
  literal=re.fullmatch(r"(\d+)'([hbd])([0-9a-fA-F]+)",expression)
  if literal:return {'op':'literal','value':int(literal[3],{'h':16,'b':2,'d':10}[literal[2]]),'width':int(literal[1])}
  if expression.startswith('{')and expression.endswith('}'):
   # All source connections used here are flat concatenations of nets/slices.
   parts=[self.resolve(path,x.strip(),trail+(key,))for x in expression[1:-1].split(',')]
   return {'op':'concat','values':parts,'width':sum(p['width']for p in parts)}
  raise ValueError('unsupported exact source expression '+str((path,expression)))

def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--adapters',type=Path,default=R/'build/memory-fabric-adapters-source-v2');p.add_argument('--output',type=Path,default=R/'build/memory-fabric-graph-v1');a=p.parse_args();out=a.output.resolve()
 if out.exists():raise ValueError('fresh graph output required')
 adapters=json.loads((a.adapters/'extraction.json').read_text());cachepath=R/'build/cache-hierarchy-source-v1/extraction.json';nocpath=R/'build/noc-network-source-v2/extraction.json';cache=json.loads(cachepath.read_text());noc=json.loads(nocpath.read_text());h=Hierarchy();components={}
 def add(name,path,fields,child=None,domain='uncore'):
  mappings=[]
  for f in fields:
   expression=h.at(path)['instances'][child]['connections'][f['name']]if child else f['name']
   if expression in ('/* unused */',''):
    assert f['direction']=='output',(name,f)
    e={'op':'unconnected','name':name+'/'+f['name'],'width':f['width']}
   else:e=h.resolve(path,expression)
   assert e['width']==f['width'],(name,f,e)
   mappings.append({**{k:f[k]for k in ['name','direction','index','width']},'source_expression':expression,'global':e})
  components[name]={'clock_domain':domain,'physical_ports':mappings}
 add('rocket_cache','tile_prci_domain_2/element_reset_domain_rockettile',cache['components']['rocket']['physical_ports'],'dcache','rocket')
 add('l2','coh_wrapper',cache['components']['l2']['physical_ports'],'l2')
 add('noc','',noc['physical_ports'])
 paths={'rocket_tile':'tile_prci_domain_2/element_reset_domain_rockettile','rocket_source':'tile_prci_domain_2','rocket_sink':'','manager':'coh_wrapper'}
 for name,info in adapters['cuts'].items():add(name,paths[name],info['physical_ports'],domain=info['clock_domain'])
 producers=collections.defaultdict(list);consumers=collections.defaultdict(list);complex_edges=[]
 for name,comp in components.items():
  for f in comp['physical_ports']:
   e=f['global'];desc={'component':name,'index':f['index'],'field':f['name'],'width':f['width']}
   if e['op']=='net':(producers if f['direction']=='output'else consumers)[e['name']].append(desc)
   else:complex_edges.append({'direction':f['direction'],**desc,'global':e})
 duplicates={n:v for n,v in producers.items()if len(v)>1};assert not duplicates,duplicates
 joins=[{'net':n,'producer':v[0],'consumers':consumers.get(n,[])}for n,v in producers.items()if n in consumers]
 external=[{'net':n,'consumers':v}for n,v in consumers.items()if n not in producers]
 result={'schema':'iris.memory_fabric_source_graph.v1','components':components,'joins':joins,'external_input_nets':external,'complex_expressions':complex_edges,'source_files':{str(p):sha(p)for p in sorted(h.used)},'input_sha256':{str(p):sha(p)for p in [Path(__file__),a.adapters/'extraction.json',cachepath,nocpath]},'source_association':'saved standalone FIR f1b36; not Ethan image attestation','added_clock_edges':0,'external_service_inferred':False,'hardware_contacted':False,'timing_certified':False}
 out.mkdir();(out/'graph.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'components':len(components),'joins':len(joins),'external_nets':len(external),'complex_expressions':len(complex_edges),'report_sha256':sha(out/'graph.json')}))
if __name__=='__main__':main()
