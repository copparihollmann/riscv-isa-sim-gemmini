#!/usr/bin/env python3
"""Audit explicit mapped RAS flop INIT and Q nets; never infer loaded-image state."""
import argparse,hashlib,json,re,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'hardware'))
from edif_ram_audit import delta,expression,name,identifier,REFERENCE,hierarchy_paths
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
REG=re.compile(r'ras_([0-5])_reg_([0-9]+)_$')
def audit(path,expected,out):
 out.mkdir(parents=True,exist_ok=False);start=time.monotonic();receipt=json.loads(path.read_text())
 assert sha(path)==expected and receipt['status']=='decoded_text_and_lexical_balance_verified'
 library=cell=None;edges={};design=None;pending=None;records=[];q_nets={};raw_evidence=[];digest=hashlib.sha256()
 for line_no,raw in enumerate((path.parent/'netlist.edf').open('rb'),1):
  digest.update(raw);line=raw.decode();head=line.lstrip()
  if pending:
   pending['lines'].append(line);pending['depth']+=delta(line)
   if pending['depth']<0:raise ValueError('expression overclosed')
   if pending['depth']:continue
   text=''.join(pending['lines']);node=expression(text);kind=pending['kind'];owner=pending['cell'];first=pending['first'];pending=None
   if kind=='design':design=node;continue
   if kind=='instance':
    key,display=identifier(node[1]);match=REG.fullmatch(key);assert match
    refs=[n for n in node[2:]if isinstance(n,list)and n and n[0]=='viewref'];assert len(refs)==1
    target=[n for n in refs[0]if isinstance(n,list)and n and n[0]=='cellref'];assert len(target)==1
    props={n[1]:n[2]for n in node[2:]if isinstance(n,list)and n and n[0]=='property'}
    assert target[0][1]=='FDRE' and props['INIT']==['string',"1'b0"],(owner,key,target,props)
    records.append({'cell':list(owner),'instance':key,'display':display,'entry':int(match[1]),'bit':int(match[2]),
      'primitive':'FDRE','explicit_INIT':props['INIT'],'lines':[first,line_no],
      'expression_sha256':hashlib.sha256(text.encode()).hexdigest()});raw_evidence.append(text)
   elif kind=='net':
    if '(portref Q (instanceref ras_'not in text:continue
    joins=[n for n in node if isinstance(n,list)and n and n[0]=='joined'];assert len(joins)==1
    refs=joins[0][1:]
    sources=[n[2][1]for n in refs if isinstance(n,list)and len(n)==3 and n[0]=='portref'and n[1]=='Q'and isinstance(n[2],list)and n[2][0]=='instanceref'and REG.fullmatch(n[2][1])]
    for source in sources:
     key=(*owner,source);assert key not in q_nets,key
     q_nets[key]={'net':identifier(node[1])[1],'lines':[first,line_no],'connections':refs,
       'expression_sha256':hashlib.sha256(text.encode()).hexdigest()}
    raw_evidence.append(text)
   continue
  if head.lower().startswith('(library ')or head.lower().startswith('(external '):library=name(head.split(' ',1)[1])[0]
  elif head.startswith('(cell '):cell=(library,name(head[6:])[0])
  elif head.startswith('(instance '):
   instance=name(head[10:])[0];ref=REFERENCE.search(head);assert ref
   child=(ref[2]or library,ref[1])
   if child[0]!='hdi_primitives':edges.setdefault(cell,[]).append((instance,child))
   if REG.fullmatch(instance):pending={'kind':'instance','lines':[line],'depth':delta(line),'cell':cell,'first':line_no}
  elif head.startswith('(net ')and cell and cell[1]in('ShuttleFrontend','ShuttleFrontend_2015'):
   depth=delta(line)
   if depth:pending={'kind':'net','lines':[line],'depth':depth,'cell':cell,'first':line_no}
  elif head.startswith('(design '):pending={'kind':'design','lines':[line],'depth':delta(line),'cell':cell,'first':line_no}
 assert pending is None and design is not None and digest.hexdigest()==receipt['decoded_edif_sha256']
 assert len(records)==480,len(records)
 cells={tuple(r['cell'])for r in records};assert len(cells)==2,cells
 for target in cells:
  bits={(r['entry'],r['bit'])for r in records if tuple(r['cell'])==target}
  assert bits=={(e,b)for e in range(6)for b in range(40)},target
 topref=[n for n in design if isinstance(n,list)and n and n[0]=='cellref'];assert len(topref)==1
 libref=[n for n in topref[0]if isinstance(n,list)and n and n[0]=='libraryref'];assert len(libref)==1
 top=(libref[0][1],topref[0][1]);paths=hierarchy_paths(top,cells,edges)
 for r in records:
  key=(*r['cell'],r['instance']);assert key in q_nets,key;r['Q_net']=q_nets[key];r['hierarchy_paths']=paths[tuple(r['cell'])]
 (out/'physical-registers-and-Q-nets.edf-fragments').write_text(''.join(raw_evidence))
 report={'schema':'iris.mapped_RAS_flop_INIT_audit.v1','pass':True,'hardware_contacted':False,
  'decode_receipt_sha256':expected,'checkpoint_sha256':receipt['checkpoint_sha256'],
  'decoded_edif_sha256':digest.hexdigest(),'source_sha256':sha(__file__),
  'explicit_FDRE_INIT_zero_bits':480,'entries_per_frontend':6,'bits_per_entry':40,
  'each_Q_net_directly_recorded':True,'registers':records,'host_seconds':time.monotonic()-start,
  'logical_state_encoding_certified':False,'routed_preservation_certified':False,
  'bitstream_loaded_state_certified':False,'source_reset_policy_changed':False,
  'scope':'Explicit synthesized FDRE properties, exhaustive entry/bit coverage, direct Q nets and actual design-root hierarchy; no inferred routed/bitstream or source-RTL initialization'}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items()if k!='registers'}))
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--decode',type=Path,required=True);p.add_argument('--sha256',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();audit(a.decode.resolve(),a.sha256,a.output.resolve())
