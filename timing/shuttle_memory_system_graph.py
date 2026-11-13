#!/usr/bin/env python3
"""Derive the two actual Shuttle tile paths joined to the frozen System pins."""
import argparse,hashlib,json,re
from pathlib import Path
import memory_fabric_graph as base
import shuttle_memory_system_extract as extract
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
class Hierarchy(base.Hierarchy):
 def load(self,mod):
  q=super().load(mod)
  if q.get('balanced_connections_parsed'):return q
  q['balanced_connections_parsed']=True
  # The source PTW port contains multiline nested parentheses; never truncate
  # a physical expression at an inner ')' followed by whitespace.
  text=Path(q['path']).read_text()
  q['instances']={x['name']:x for x in extract.instances(text)}
  q['aliases'].update({n:e.strip()for n,e in re.findall(r'^\s*wire\s+(?:\[[^]]+\]\s+)?(\w+)\s*=\s*([^;]+);',text,re.M)})
  return q

def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve()
 if out.exists():raise ValueError('fresh graph required')
 source=json.loads((a.source/'extraction.json').read_text());old=R/'build/memory-fabric-graph-v1/graph.json';g=json.loads(old.read_text());sp=R/'build/serial-memory-system-check-v4/physical-port-schema.stdout';schema=json.loads(sp.read_text());serialpath=R/'build/serial-memory-source-v3/extraction.json';serial=json.loads(serialpath.read_text());cachepath=R/'build/cache-hierarchy-source-v1/extraction.json';cache=json.loads(cachepath.read_text());h=Hierarchy();components={}
 def resolve(path,expr,width):
  if not re.sub(r'/\*.*?\*/','',expr).strip():return {'op':'unconnected','name':path+'/'+expr,'width':width}
  e=h.resolve(path,expr);assert e['width']==width,(path,expr,width,e);return e
 sf=[];exports={x['wrapper']:x for x in serial['physical_exports']}
 for direction in ['input','output']:
  for f in schema[direction+'s']:
   n=f['name'];e=None
   if n.startswith('fabric/'):
    raw=n[7:]
    if direction=='input':e={'op':'net','name':raw,'width':f['width']}
    else:
     component,field=raw.split('::',1);e=next(x['global']for x in g['components'][component]['physical_ports']if x['direction']=='output'and x['name']==field)
   else:
    raw=n[5:];export=exports.get(raw)
    if export and export['component']=='mbus':
     expr=h.at('')['instances']['mbus']['connections'][export['port']];e=resolve('',expr,f['width'])
    else:e={'op':'net','name':'SerialPath/'+raw,'width':f['width']}
   sf.append({**f,'direction':direction,'global':e})
 components['system']={'clock_domain':'existing_rocket_uncore_bringup_serial','physical_ports':sf}
 for hart in range(2):
  parent='tile_prci_domain'+('_1'if hart else'');tile=parent+'/element_reset_domain_shuttle_tile';assert h.at(tile)
  for kind,path in [('cache',tile),('tile',tile),('prci',parent),('uncore','')]:
   if kind=='cache':fields=cache['components']['shuttle']['physical_ports'];inst=h.at(path)['instances']['dcache']
   else:fields=source['cuts'][kind]['physical_ports'];inst=None
   fs=[]
   for f in fields:
    expr=inst['connections'][f['name']]if inst else f['name']
    # The second SBUS coupler is a distinct instance of the same module.
    if kind=='uncore'and hart:
     first=h.at('')['instances']['sbus_coupler_to_shuttle_tile']['connections'];second=h.at('')['instances']['sbus_coupler_to_shuttle_tile_1']['connections'];remap={}
     for pin,original in first.items():
      aa=re.findall(r'\b[A-Za-z_]\w*\b',original);bb=re.findall(r'\b[A-Za-z_]\w*\b',second[pin]);assert len(aa)==len(bb),(pin,original,second[pin])
      for old_name,new_name in zip(aa,bb):
       if old_name in remap:assert remap[old_name]==new_name
       remap[old_name]=new_name
     expr=re.sub(r'\b[A-Za-z_]\w*\b',lambda m:remap.get(m[0],m[0]),expr)
    e=resolve(path,expr,f['width']);fs.append({**{k:f[k]for k in ['name','direction','index','width']},'source_expression':expr,'global':e})
   components['shuttle'+str(hart)+'_'+kind]={'clock_domain':'uncore','physical_ports':fs}
 # The source hart-ID nexus is combinational constant wiring. Keep those
 # source-assigned IDs internal; caller zero-fill must never turn hart1 into0.
 nexus=h.at('')['instances']['tileHartIdNexusNode'];nexus_body=h.load(nexus['module']);constant_bindings={}
 for port,connection in nexus['connections'].items():
  if port in nexus_body['aliases']:
   value=h.resolve('tileHartIdNexusNode',nexus_body['aliases'][port]);assert value['op']=='literal'
   global_net=h.resolve('',connection);assert global_net['op']=='net'
   constant_bindings[global_net['name']]=value
 def bind_constants(e):
  if e['op']=='net':return constant_bindings.get(e['name'],e)
  if e['op']=='slice':return {**e,'value':bind_constants(e['value'])}
  if e['op']=='concat':return {**e,'values':[bind_constants(x)for x in e['values']]}
  return e
 for c in components.values():
  for f in c['physical_ports']:f['global']=bind_constants(f['global'])
 producers={};aliases=[]
 def key(e):return e['name']if e['op']=='net'else None
 for cn,c in components.items():
  for f in c['physical_ports']:
   n=key(f['global'])
   if n and f['direction']=='output':
    if n in producers:aliases.append({'net':n,'producer':producers[n],'equivalent_observation':{'component':cn,'index':f['index']}})
    else:producers[n]={'component':cn,'index':f['index'],'name':f['name'],'width':f['width']}
 result={'schema':'iris.shuttle_memory_source_graph.v1','components':components,'producer_aliases':aliases,'source_constant_nexus_bindings':constant_bindings,'source_files':{str(p):sha(p)for p in sorted(h.used)},'input_sha256':{str(p):sha(p)for p in [Path(__file__),R/'timing/shuttle_memory_system_extract.py',R/'timing/memory_fabric_graph.py',a.source/'extraction.json',old,sp,serialpath,cachepath]},'source_clock_domains':['uncore','rocket','bringup','serial'],'added_clock_edges':0,'source_image_association_verified':False,'hardware_contacted':False,'timing_certified':False}
 out.mkdir();(out/'graph.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'components':len(components),'producer_aliases':len(aliases),'report_sha256':sha(out/'graph.json')}))
if __name__=='__main__':main()
