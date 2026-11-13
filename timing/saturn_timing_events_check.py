#!/usr/bin/env python3
"""Typed C++ physical events versus the independent Python stage/protocol ledger."""
import argparse,hashlib,importlib.util,json,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1];REFERENCE=R/'build/saturn-timing-component-v1-final';FAST=R/'build/saturn-timing-fast-component-v1-final'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def expected_mix(events,rows,profile,hart):
 mix=1469598103934665603;checks=0;kinds={'EX_candidate':0,'EX_fire':1,'MEM_kill':2,'COM_front_token':3};prefix='io_core_'if profile=='rocket'else'io_'
 for e in events:
  if 'id'not in e:continue
  i=rows[e['ex_edge']];v=prefix+'ex_vconfig_';fields=[kinds[e['kind']],e['edge'],e['id'],hart,e['pc'],e['inst'],int(e['fired']),i[v+'vl'],i[prefix+'ex_vstart'],i[v+'vtype_vsew'],i[v+'vtype_vlmul_sign'],i[v+'vtype_vlmul_mag'],i[v+'vtype_tm']if profile=='compute'else 255,i[v+'vtype_tk']if profile=='compute'else 255,42]
  for word in fields:mix=((mix^word)*1099511628211)&((1<<64)-1)
  checks+=1
 return mix,checks
def expected_tl_mix(events,rows,physical,profile):
 bus=8 if profile=='rocket'else 32;pending={};mix=1469598103934665603
 for e in events:
  if e['kind']not in['TL_A_beat','TL_D_beat']:continue
  edge=e['edge'];i,o=rows[edge],physical[edge];source=e['source'];is_a=e['kind']=='TL_A_beat';data=[0]*4;masks=[0]*4
  if is_a:
   if e['beat']==1:pending[source]={'edge':edge,'address':e['address'],'size':e['size'],'opcode':e['opcode']}
   owner=pending[source];opcode=e['opcode'];size=e['size'];byte_mask=o['auto_atl_out_a_bits_mask']
   if opcode in[0,1]:
    for w in range(bus//8):
     data[w]=o['auto_atl_out_a_bits_data'+(''if profile=='rocket'else'_'+str(w))];masks[w]=sum(255<<(8*b)for b in range(8)if byte_mask>>(8*w+b)&1)
  else:
   owner=pending[source];opcode=e['opcode'];size=owner['size'];byte_mask=0
   if opcode==1:
    byte_count=1<<size;offset=owner['address']%bus if byte_count<bus else 0
    for w in range(bus//8):
     data[w]=i['auto_atl_out_d_bits_data'+(''if profile=='rocket'else'_'+str(w))];masks[w]=int.from_bytes(bytes(255 if byte_count>=bus or offset<=8*w+b<offset+byte_count else 0 for b in range(8)),'little')
  words=[12 if is_a else 13,edge,source,opcode,size,owner['address'],e['beat'],e['total'],owner['edge'],byte_mask]
  for w in range(4):words.extend([data[w]&masks[w],masks[w]])
  for word in words:mix=((mix^word)*1099511628211)&((1<<64)-1)
  if not is_a and e['beat']==e['total']:del pending[source]
 return mix
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);sdk=FAST/'build/saturn-timing-fast-v1/sdk/sdk';source=R/'timing/saturn_timing_events.cpp';header=source.with_suffix('.hpp');driver=R/'timing/saturn_timing_events_driver.cpp';common=['/usr/bin/g++','-O3','-std=c++20','-I'+str(sdk),'-I'+str(R/'timing')];commands=[common+['-c',str(source),'-o',str(out/'events.o')],['/usr/bin/ar','rcs',str(out/'libiris_saturn_events.a'),str(out/'events.o')],common+[str(driver),str(out/'libiris_saturn_events.a'),str(sdk/'libiris_saturn_timing.a'),'-pthread','-latomic','-o',str(out/'events')]]
 with(out/'build.log').open('w')as log:
  for command in commands:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
 helper=REFERENCE/'timing/saturn_timing_check.py';spec=importlib.util.spec_from_file_location('independent_saturn_reference',helper);check=importlib.util.module_from_spec(spec);spec.loader.exec_module(check);check.R=REFERENCE;profiles={k:json.loads((REFERENCE/'build/saturn-timing-source-v1'/k/'ports.json').read_text())for k in['compute','rocket']};inputs=[Path(__file__),source,header,driver,sdk/'saturn_timing.hpp',sdk/'libiris_saturn_timing.a',FAST/'report.json',REFERENCE/'report.json',helper,Path('/usr/bin/g++'),Path('/usr/bin/ar')];reports=[];mutations=[]
 for case in['vme','rvv','fpcomp','shared-fpu']:
  raw=REFERENCE/'build/saturn-timing-rtl-v1'/(case+'.stderr');rows,gold,times=check.capture(raw,profiles);inputs.append(raw)
  for h in range(3):
   profile='rocket'if h==2 else'compute';folder=FAST/'build/saturn-timing-fast-replay-v1'/case;ports=folder/f'hart{h}.input';values=folder/f'hart{h}.stdout';inputs.extend([ports,values]);command=[str(out/'events'),profile,str(h),str(ports),str(values)];q=subprocess.run(command,capture_output=True,text=True,timeout=60);label=case+'-h'+str(h);(out/(label+'.stdout')).write_text(q.stdout);(out/(label+'.stderr')).write_text(q.stderr)
   if q.returncode:raise ValueError('Typed physical ledger failed '+label+' '+q.stderr)
   actual=json.loads(q.stdout);ledger=check.Timeline(profile)
   for e,(i,o,tb)in enumerate(zip(rows[h],gold[h],times[h])):ledger.observe(e,tb,i,o)
   mix,count=expected_mix(ledger.events,rows[h],profile,h)
   tl_mix=expected_tl_mix(ledger.events,rows[h],gold[h],profile)
   if actual['edges']!=len(rows[h])or actual['source_events']!=dict(ledger.stats)or actual['pending_TL_sources_at_end']!=len(ledger.pending)or actual['command_identity_mix64']!=mix or actual['command_identity_checks']!=count or actual['TL_owned_data_mask_mix64']!=tl_mix:raise ValueError('Independent command/protocol identity/data mask differs '+label)
   reports.append({'case':case,'hart':h,'argv':command,**actual})
   if case=='rvv'and h==2:
    ilines=ports.read_text().splitlines();olines=[x for x in values.read_text().splitlines()if x.startswith('SATURN_FRAME ')];names=[f['word_name']for f in profiles[profile]['words']['input']];first_a=next(e for e,(i,o)in enumerate(zip(rows[h],gold[h]))if o['auto_atl_out_a_valid']and i['auto_atl_out_a_ready']);first_d=next(e for e,(i,o)in enumerate(zip(rows[h],gold[h]))if i['auto_atl_out_d_valid']and o['auto_atl_out_d_ready'])
    # A.size is an output, so mutate that source-owned field in the physical
    # output transcript, rather than inventing an input readiness or queue state.
    ofields=[f['word_name']for f in profiles[profile]['words']['output']];ochange=olines[:];parts=ochange[first_a].split();idx=2+ofields.index('auto_atl_out_a_bits_size');parts[idx]=str(int(parts[idx])^1);ochange[first_a]=' '.join(parts);wrong_o=out/'wrong-A-size.stdout';wrong_o.write_text('\n'.join(ochange)+'\n')
    change=ilines[:];parts=change[first_d].split();parts[2+names.index('auto_atl_out_d_bits_source')]='63';change[first_d]=' '.join(parts);wrong_i=out/'wrong-D-source.input';wrong_i.write_text('\n'.join(change)+'\n');truncated=out/'truncated.stdout';truncated.write_text('\n'.join(olines[:-1])+'\n')
    overwide_i=out/'overwide-reset.input';change=ilines[:];parts=change[0].split();parts[2+names.index('reset')]='2';change[0]=' '.join(parts);overwide_i.write_text('\n'.join(change)+'\n');overwide_o=out/'overwide-output.stdout';change=olines[:];parts=change[0].split();parts[2+ofields.index('auto_atl_out_a_valid')]='2';change[0]=' '.join(parts);overwide_o.write_text('\n'.join(change)+'\n')
    unseeded_i=out/'no-reset-history.input';unseeded_o=out/'no-reset-history.stdout';after=next(e for e,i in enumerate(rows[h])if not i['reset']);parts=ilines[after].split();parts[1]='0';unseeded_i.write_text(' '.join(parts)+'\n');parts=olines[after].split();parts[1]='0';unseeded_o.write_text(' '.join(parts)+'\n')
    for name,ip,op,hart in[('wrong-A-size',ports,wrong_o,2),('unowned-D-source',wrong_i,values,2),('missing-edge',ports,truncated,2),('wrong-hart-profile',ports,values,0),('overwide-input',overwide_i,values,2),('overwide-output',ports,overwide_o,2),('missing-reset-history',unseeded_i,unseeded_o,2)]:
     reject=subprocess.run([str(out/'events'),profile,str(hart),str(ip),str(op)],capture_output=True,text=True,timeout=60)
     if reject.returncode!=2:raise ValueError('Typed ledger missed corruption '+name)
     mutations.append({'name':name,'exit_status':reject.returncode,'diagnostic':reject.stderr})
  del rows,gold,times
 target=out/'sdk';target.mkdir();shutil.copy2(header,target/header.name);shutil.copy2(out/'libiris_saturn_events.a',target/'libiris_saturn_events.a');(out/'source').mkdir()
 for p in[Path(__file__),source,header,driver]:shutil.copy2(p,out/'source'/p.name)
 report={'schema':'iris.saturn_typed_physical_event_projection.v1','pass':True,'runs':reports,'corruption_refusals':mutations,'argv':commands,'input_sha256':{str(p):sha(p)for p in inputs},'native_sha256':sha(out/'events'),'library_sha256':sha(target/'libiris_saturn_events.a'),'actual_source_core_edges':sum(r['edges']for r in reports),'command_identity_checks':sum(r['command_identity_checks']for r in reports),'TL_event_checks':sum(r['TL_event_checks']for r in reports),'projection_drives_internal_state_or_ready':False,'TL_events_have_invented_PC_owner':False,'front_token_is_async_completion':False,'internal_VAT_to_memory_or_VRF_event_correlation_certified':False,'snapshot_or_unreset_projection_supported':False,'hardware_contacted':False};report['artifact_sha256']={str(p.relative_to(out)):sha(p)for p in out.rglob('*')if p.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k]for k in['actual_source_core_edges','command_identity_checks','TL_event_checks','native_sha256']}));print(sha(out/'report.json'))
if __name__=='__main__':main()
