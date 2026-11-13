#!/usr/bin/env python3
"""Create an uncalibrated diagnostic by changing14 explicit family cost lines."""
import argparse,hashlib,json,re
from pathlib import Path
FAMILIES={'rvv.integer','rvv.fadd.fp16','rvv.fadd.fp32','rvv.fadd.fp64','memory.vector.load','memory.vector.store','vme.row_move'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();parent=a.parent.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);raw=parent.read_text();lines=raw.splitlines(keepends=True);changed=[];seen=set();result=[]
 for index,line in enumerate(lines):
  tokens=list(re.finditer(r'\S+',line));words=[x.group()for x in tokens]
  if len(words)==11 and words[0]=='empirical_family'and words[1]in('0','1')and words[2]in FAMILIES:
   key=(int(words[1]),words[2]);assert key not in seen;seen.add(key);new=line[:tokens[4].start()]+'0'+line[tokens[4].end():tokens[5].start()]+'0'+line[tokens[5].end():];changed.append({'line':index+1,'hart':key[0],'family':key[1],'setup_before':words[4],'work_before':words[5],'setup_after':'0','work_after':'0','resource_preserved':words[3],'interval_preserved':words[6],'original_line':line.rstrip('\n'),'new_line':new.rstrip('\n')});result.append(new)
  else:result.append(line)
 assert seen=={(h,f)for h in(0,1)for f in FAMILIES}and len(changed)==14
 text=''.join(result);child=out/'zero-adjustment.fixture';child.write_text(text)
 # Compare after removing only the two authorized token spans; every other
 # byte, including OPU mode, cache/transport, intervals and identity survives.
 def masked(value):
  answer=[]
  for line in value.splitlines(keepends=True):
   ts=list(re.finditer(r'\S+',line));ws=[x.group()for x in ts]
   if len(ws)==11 and ws[0]=='empirical_family'and ws[1]in('0','1')and ws[2]in FAMILIES:line=line[:ts[4].start()]+'COST'+line[ts[4].end():ts[5].start()]+'COST'+line[ts[5].end():]
   answer.append(line)
  return ''.join(answer)
 assert masked(raw)==masked(text)
 assert [l for l in text.splitlines()if l.startswith('empirical_opu_entry ')]==['empirical_opu_entry source-VDQ4-IQ3-entry-MM-TK124-COMplus1-v3']
 profiles=[l.split()for l in text.splitlines()if l.startswith('empirical_profile ')];assert len(profiles)==1 and len(profiles[0])==4 and profiles[0][3]=='bounded'
 report={'schema':'iris.C12_compute1320_zero_adjustment_derivation.v1','pass':True,'parent':str(parent),'parent_sha256':sha(parent),'fixture':str(child),'fixture_sha256':sha(child),'changed_family_lines':changed,'exactly14_lines':True,'only_setup_and_work_tokens_changed':True,'all_other_bytes_identical':True,'calibration_identity_intentionally_inherited_metadata_only':profiles[0][2],'calibration_or_quality_transfer_claimed':False,'parameters_fitted':False,'memory_cache_transport_II_and_hart2_preserved':True,'OPU_controller_and_selector_preserved':True,'explicit_vector_load_store_family_adjustments_also_zeroed':True,'hardware_or_reference_timings_consumed':False,'hardware_contacted':False,'input_sha256':{str(parent):sha(parent),str(Path(__file__).resolve()):sha(Path(__file__).resolve())}}
 (out/'derivation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'fixture_sha256':sha(child),'derivation_sha256':sha(out/'derivation.json')}))
if __name__=='__main__':main()
