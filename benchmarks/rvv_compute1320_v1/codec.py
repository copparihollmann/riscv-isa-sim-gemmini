"""Strict ASCII-base6417actualuint64LE wire decoder. Geometry is compiled metadata.
No record padding, invented counters, timing substitutions, or physical-traffic claims.
"""
import base64,binascii,json,re,struct
FIELDS=['case_index','hart','start_cycle','issue_cycle','end_cycle','ir0','ir1','ir2','checksum','expected_checksum','mismatch_or','checked_words','vl','mtime_before','mtime_after','msip_before','msip_after']
def need(ok,msg):
 if not ok:raise ValueError(msg)
def expand(text,c,partial=False):
 need(partial or text.endswith('\n'),'Complete newline terminated compact stream');out=[];index=0;active=None;count=0;next_h=0;done=False;sections=[]
 for line in text.splitlines():
  if line.startswith('IRIS_HART_BEGIN '):
   r=json.loads(line.split(' ',1)[1]);need(active is None and next_h<2 and r==dict(hart=next_h,regions=sum(x['hart']==next_h for x in c['cases']))and all(type(v)is int for v in r.values()),'Typed ordered compact phaseheader');active=next_h;count=0;continue
  if line.startswith('IRIS_BIN '):
   bits=line.split(' ');need(len(bits)==3 and re.fullmatch(r'0|[1-9][0-9]*',bits[1])is not None and int(bits[1])==index and active is not None and index<len(c['cases']),'Compact actual caseindex/order/phase');payload=bits[2];need(len(payload)==184,'Exactly184base64chars')
   try:raw=base64.b64decode(payload,validate=True)
   except(binascii.Error,ValueError)as e:raise ValueError('Strictbase64')from e
   need(len(raw)==136 and base64.b64encode(raw).decode()==payload,'Canonical136Bpayload,nopaddingbytes');v=dict(zip(FIELDS,struct.unpack('<17Q',raw)));case=c['cases'][index];need(v['case_index']==index and v['hart']==active==case['hart'],'Actual payload index/hart agrees compiled role')
   r=dict(case_id=case['case_id'],parent_case_id=case['parent_case_id'],suite='rvv_identify',region='kernel',hart=v['hart'],trial_id=case['trial_id'],kind=case['kind_id'],sew=case['sew'],lmul=case['lmul'],mode=case['mode'],operations=case['n'],vector_bytes=case['bytes'],vl=v['vl'],checked_words=v['checked_words'],mismatch_or=v['mismatch_or'],start_cycle=v['start_cycle'],issue_cycle=v['issue_cycle'],end_cycle=v['end_cycle'],instret_delta=v['ir2']-v['ir0'],issue_instret_delta=v['ir1']-v['ir0'],drain_instret_delta=v['ir2']-v['ir1'],mtime_before=v['mtime_before'],mtime_after=v['mtime_after'],msip_before=v['msip_before'],msip_after=v['msip_after'],checksum=v['checksum'],expected_checksum=v['expected_checksum'],**{'pass':v['mismatch_or']==0 and v['checksum']==v['expected_checksum']and v['msip_before']==v['msip_after']==0},data_origin='DecodedIRIS_BIN17actualuint64LE136B;geometryfromcompiledcase',actual_record_uint64=list(struct.unpack('<17Q',raw)))
   out.append('IRIS_REGION '+json.dumps(r,separators=(',',':')));index+=1;count+=1;continue
  if line.startswith('IRIS_HART_SECTION '):
   r=json.loads(line.split(' ',1)[1]);need(active is not None and set(r)=={'hart','regions','failed'}and all(type(v)is int for v in r.values())and r['hart']==active and r['regions']==count==sum(x['hart']==active for x in c['cases'])and 0<=r['failed']<=count,'Complete compact phasefooter');sections.append(r);out.append(line);active=None;next_h+=1;continue
  if line.startswith('IRIS_BATCH_DONE '):
   need(not done and active is None and next_h==2 and index==len(c['cases']),'AlltwocompactphasesbeforeDone');done=True;out.append(line);continue
  if line.startswith('IRIS_REGION '):raise ValueError('RawstreammustnotcontainfabricatedJSONregions')
  if line.startswith('IRIS_FATAL'):out.append(line)
 need(partial or(done and next_h==2 and index==1320),'Fullcompact1320completion');return '\n'.join(out)+'\n'
