#!/usr/bin/env python3
"""Freeze pinned issue/decode sources and generate scalar control templates.

This audits source structure; it does not fit or certify cycle parameters.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
SPECS={
    'chipyard':('third_party/chipyard','b4542facf6cc9457f6e358e8f80a8b3a0ff5df19'),
    'shuttle':('third_party/shuttle','a536ed1df91a0f65770e36758291d02a8cb929c4'),
    'rocket':('third_party/rocket-chip','fc745a8c377fdbf1d278eea81da9ac47b4b5fbc0'),
    'saturn':('third_party/saturn','536774bd4c5e3bcd7813a4a0dc72fc87e5818532'),
}
FILES={
    'iris-config':('chipyard','generators/chipyard/src/main/scala/config/IrisConfigs.scala'),
    'shuttle-config':('shuttle','src/main/scala/common/Configs.scala'),
    'shuttle-params':('shuttle','src/main/scala/common/Parameters.scala'),
    'shuttle-core':('shuttle','src/main/scala/exu/Core.scala'),
    'shuttle-uop':('shuttle','src/main/scala/common/MicroOp.scala'),
    'shuttle-fetch':('shuttle','src/main/scala/ifu/FetchBuffer.scala'),
    'shuttle-frontend':('shuttle','src/main/scala/ifu/Frontend.scala'),
    'scalar-decode':('rocket','src/main/scala/rocket/IDecode.scala'),
    'instructions':('rocket','src/main/scala/rocket/Instructions.scala'),
    'custom-instructions':('rocket','src/main/scala/rocket/CustomInstructions.scala'),
    'matrix-config':('rocket','src/main/scala/rocket/Matrix.scala'),
    'fpu-decode':('rocket','src/main/scala/tile/FPU.scala'),
    'rocket-core':('rocket','src/main/scala/rocket/RocketCore.scala'),
    'rocket-btb':('rocket','src/main/scala/rocket/BTB.scala'),
    'saturn-integration':('saturn','src/main/scala/shuttle/Configs.scala'),
}
CLASSES=('MDecode','M64Decode','ADecode','A64Decode','FDecode','F64Decode',
         'DDecode','D64Decode','HDecode','H64Decode','HDDecode','I64Decode',
         'SVMDecode','DebugDecode','FenceIDecode','ZbaDecode','Zba64Decode',
         'ZbbDecode','Zbb64Decode','ZbsDecode','IDecode','VCFGDecode','MatrixCFGDecode')
FIELDS={
    'FP':1,'ROCC':2,'BRANCH':3,'JAL':4,'JALR':5,'RXS1':7,'RXS2':6,
    'WXD':21,'MEM':13,'MUL':19,'DIV':20,'FENCE':24,'FENCE_I':23,'AMO':25,
    'RFS1':15,'RFS2':16,'RFS3':17,'WFD':18,
}
FLAGS=('FP','ROCC','BRANCH','JAL','JALR','RXS1','RXS2','WXD','MEM','MUL','DIV',
       'CSR_EN','SYSTEM','CSR_ANY','FENCE','FENCE_I','AMO','SFENCE','USES_FP',
       'SETS_VCFG','VECTOR','RFS1','RFS2','RFS3','WFD')


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def text_sha(text):return hashlib.sha256(text.encode()).hexdigest()


def block(text,name):
    match=re.search(r'\bclass\s+'+re.escape(name)+r'\b',text)
    if not match:raise ValueError('missing decoder class '+name)
    start=text.index('{',match.end());depth=1;at=start+1
    while depth:
        if text[at]=='{':depth+=1
        if text[at]=='}':depth-=1
        at+=1
    return text[start+1:at-1],text.count('\n',0,start)+1


def patterns(text):
    found={}
    for match in re.finditer(r'def\s+(\w+)\s*=\s*BitPat\("b([01?_]+)"\)',text):
        bits=match[2].replace('_','')
        if len(bits)!=32:continue
        value=int(bits.replace('?','0'),2)
        mask=int(''.join('0' if b=='?' else '1' for b in bits),2)
        record=(mask,value)
        if match[1] in found and found[match[1]]!=record:raise ValueError('ambiguous pattern '+match[1])
        found[match[1]]=record
    return found


def decode_rows(sources):
    pats={}
    for key in ('instructions','custom-instructions','matrix-config'):
        for name,value in patterns(sources[key]).items():
            if name in pats and pats[name]!=value:raise ValueError('duplicate encoding '+name)
            pats[name]=value
    fp={}
    fpu=sources['fpu-decode']
    for match in re.finditer(r'(\w+)\s*->\s*List\(([^\n]*?)\)',fpu):
        values=[s.strip() for s in match[2].split(',')]
        if len(values)==17:fp[match[1]]=values
    rows=[]
    for cls in CLASSES:
        body,first=block(sources['scalar-decode'],cls)
        for match in re.finditer(r'(\w+)\s*->\s*List\((.*?)\)',body,re.S):
            name=match[1];values=[s.strip() for s in match[2].split(',')]
            if len(values)!=27:raise ValueError('decoder field count '+cls+' '+name)
            substitutions={'M':'Y','D':'N','v':'N','cmd':'M_X'}
            values=[substitutions.get(v,v) for v in values]
            if values[0]!='Y' or name not in pats:raise ValueError('unparsed enabled decoder '+name)
            mask,match_bits=pats[name];flags=[];ignored=[]
            for flag,index in FIELDS.items():
                value=values[index]
                if value=='X':
                    # Only unused system-instruction rs1 is don't-care in the
                    # selected flags. Its entire field is fixed zero.
                    if flag=='RXS1' and mask&0xf8000==0xf8000 and match_bits&0xf8000==0:
                        ignored.append('RXS1 masked by fixed rs1=x0');value='N'
                    else:raise ValueError('unresolved relevant control '+name+' '+flag)
                if value not in ('Y','N'):raise ValueError('unknown bool '+name+' '+flag+'='+value)
                if value=='Y':flags.append(flag)
            csr=values[22]
            if csr!='CSR.N':flags.append('CSR_ANY')
            if csr in ('CSR.S','CSR.C','CSR.W'):flags.append('CSR_EN')
            if csr=='CSR.I':flags.append('SYSTEM')
            if csr not in ('CSR.N','CSR.I','CSR.S','CSR.C','CSR.W'):raise ValueError('unknown CSR mode')
            if values[14]=='M_SFENCE':flags.append('SFENCE')
            if 'FP' in flags:
                if name not in fp or fp[name][0] not in ('Y','N') or fp[name][1] not in ('Y','N'):
                    raise ValueError('missing FPU ldst/wen controls '+name)
                if not (fp[name][0]=='Y' and fp[name][1]=='Y'):flags.append('USES_FP')
            if cls in ('VCFGDecode','MatrixCFGDecode'):flags.append('SETS_VCFG')
            rows.append({'name':name,'class':cls,'mask':mask,'match':match_bits,
                         'flags':flags,'ignored_dont_cares':ignored,
                         'line':first+body.count('\n',0,match.start())})
    for i,a in enumerate(rows):
        for b in rows[i+1:]:
            if ((a['match']^b['match'])&(a['mask']&b['mask']))==0:
                raise ValueError('enabled scalar pattern overlap: '+a['name']+'/'+b['name'])
    return rows


def cite(source,start,end=None):return {'source':source,'lines':[start,end or start]}


def render_header(rows):
    header='// Generated from frozen enabled RTL scalar control tables; architectural legality is separate.\n'
    header+='static constexpr DecodeRow decode_rows[] = {\n'
    for row in rows:
        control='|'.join(row['flags']) or '0'
        header+=f'  {{0x{row["mask"]:08x}u,0x{row["match"]:08x}u,{control},"{row["name"]}"}},\n'
    return header+'};\n'


def facts():
    return {
      'issue_widths':{'value':{'hart0':2,'hart1':2,'hart2':1},'evidence':[cite('iris-config',285,300),cite('shuttle-config',14,39),cite('rocket-core',66,69)]},
      'shuttle_fetch':{'value':{'parcels_per_fetch':4,'bytes_per_parcel':2,'fetch_buffer_uops':7},'evidence':[cite('shuttle-params',29,49),cite('shuttle-fetch',16,24)]},
      'retimed_alu':{'value':{'enabled_mem_alu':True,'enabled_late_alu':True,'ALU_consumer_of_lane0_ALU':'MEM','ALU_consumer_of_lane0_memory':'WB','ordinary_ALU':'EX'},'evidence':[cite('shuttle-params',29,30),cite('shuttle-core',315,382),cite('shuttle-core',863,908),cite('shuttle-core',1221,1234),cite('shuttle-core',1273,1280)]},
      'alu_uses':{'description':'wxd excludes mem/div/mul/CSR/FP/RoCC/jalr/vector; JAL is not excluded','evidence':[cite('shuttle-uop',71,78)]},
      'integer_hazards':{'description':'Older integer scoreboard/bypass hazards plus same-packet RAW/WAW. x0 suppresses final dependency hazards. X->M depends on MEM lane1 not already retaining a late ALU. Same-packet branch/config consumers cannot forward. Raw field hits can retime unused operands. ALU-producer WAW is permitted; memory-producer WAW needs LateALU.','evidence':[cite('shuttle-core',300,382)]},
      'bypass_priority':{'value':['long-latency','WB lanes0,1','COM lanes0,1','MEM lanes0,1','EX lanes0,1'],'last_matching_entry_wins':True,'evidence':[cite('shuttle-core',99,111),cite('shuttle-core',300,309)]},
      'packet_limits':{'description':'Pipe0-only classes, one memory/branch/config per packet, in-order prefix, CSR/system/exception youngest, conditional fence drain. Fence need not be youngest.','evidence':[cite('shuttle-core',435,484)]},
      'vector_config_issue':{'value':{'issueVConfig':False,'inflight_state_required':True},'evidence':[cite('saturn-integration',29,43),cite('shuttle-core',414,434),cite('shuttle-core',453,475)]},
      'frontend_metadata':{'description':'Predicted next-PC tags can reserve branch port even on non-CFI. Small-forward branch heuristic uses displacement4 for RVC or6 for full instruction, when prediction tag absent; only compressed ALU shadow can use lane1.','evidence':[cite('shuttle-fetch',36,54),cite('shuttle-core',326,326),cite('shuttle-core',447,481)]},
      'branch_resolution':{'value':'MEM stage; misprediction flushes RRD/EX and may kill younger packet lanes','evidence':[cite('shuttle-core',696,742),cite('shuttle-core',829,850)]},
      'retirement':{'description':'COM retire count is PopCount of nonexception/nonreplay/nonkilled lanes. LateALU result written in WB; miss requires replay. Interrupt/trap/CSR flush precision cannot be approximated by unconditional execution of both candidate handlers.','evidence':[cite('shuttle-core',990,1001),cite('shuttle-core',1187,1206),cite('shuttle-core',1221,1234),cite('shuttle-core',1273,1285)]},
      'internal_latency_parameters':{'value':{'pipelined_multiplier_stages':2,'scalar_sfmaLatency':4,'scalar_dfmaLatency':4},'interpretation':'Structural source parameters only; not total issue-to-retirement or calibrated cycles','evidence':[cite('shuttle-params',44,45),cite('shuttle-core',581,586)]},
      'branch_prediction_structure':{'value':{'BTB_entries':32,'BHT_entries':512,'BHT_counter_bits':2,'BHT_history_bits':8,'BHT_hash_history_bits':3,'RAS_entries':6},'evidence':[cite('shuttle-config',26,27),cite('rocket-btb',13,24)]},
    }


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--verify',action='store_true')
    parser.add_argument('--verify-live',action='store_true')
    args=parser.parse_args(); evidence=HERE/'shuttle-evidence'; audit_path=HERE/'shuttle_issue_sources.json'
    if args.verify or args.verify_live:
        audit=json.loads(audit_path.read_text())
        snapshots={}
        for key,entry in audit['sources'].items():
            if sha(HERE/entry['snapshot'])!=entry['sha256']:raise ValueError('snapshot changed: '+key)
            if args.verify_live and sha(ROOT/entry['live_path'])!=entry['sha256']:raise ValueError('live source changed: '+key)
            snapshots[key]=(HERE/entry['snapshot']).read_text()
        if sha(HERE/'shuttle_decode_rows.inc')!=audit['decoder_header_sha256']:raise ValueError('generated decoder changed')
        if sha(Path(__file__))!=audit['generator_sha256']:raise ValueError('generator changed')
        expected=decode_rows(snapshots)
        if audit['rows']!=expected or audit['scalar_rows']!=len(expected) or audit['scalar_classes']!=list(CLASSES):
            raise ValueError('decoder metadata differs from actual enabled source tables')
        if (HERE/'shuttle_decode_rows.inc').read_text()!=render_header(expected):
            raise ValueError('decoder header differs from source regeneration')
        if audit['facts']!=facts():raise ValueError('issue fact declaration changed')
        for fact in audit['facts'].values():
            for ref in fact['evidence']:
                start,end=ref['lines']
                if not 1<=start<=end<=len(snapshots[ref['source']].splitlines()):
                    raise ValueError('source fact citation out of bounds')
        elaboration=audit['elaboration']
        if sha(HERE/elaboration['excerpt'])!=elaboration['excerpt_sha256']:raise ValueError('elaboration excerpt changed')
        if args.verify_live and sha(elaboration['full_file'])!=elaboration['full_sha256']:
            raise ValueError('live elaboration changed')
        print(json.dumps({'status':'source_integrity_passed','sources':len(audit['sources']),'scalar_rows':audit['scalar_rows'],'rtl_certified':False}))
        return
    for name,(directory,pin) in SPECS.items():
        actual=subprocess.check_output(['git','-C',str(ROOT/directory),'rev-parse','HEAD'],text=True).strip()
        if actual!=pin:raise ValueError('source pin mismatch '+name)
    evidence.mkdir(exist_ok=True); sources={}; entries={}
    previous=json.loads(audit_path.read_text()) if audit_path.exists() else None
    for name,(repository,path) in FILES.items():
        live=ROOT/SPECS[repository][0]/path; snapshot=evidence/(name+'.scala')
        if previous and name in previous['sources'] and sha(live)!=previous['sources'][name]['sha256']:
            raise ValueError('source changed; re-audit required before replacing frozen evidence: '+name)
        snapshot.write_bytes(live.read_bytes()); sources[name]=snapshot.read_text()
        entries[name]={'snapshot':str(snapshot.relative_to(HERE)),'live_path':str(live.relative_to(ROOT)),
                       'sha256':sha(snapshot),'repository':repository,'commit':SPECS[repository][1]}
    rows=decode_rows(sources)
    (HERE/'shuttle_decode_rows.inc').write_text(render_header(rows))
    # Bind exact local elaboration dimensions/forwarding, without copying >100MiB.
    manifest=json.loads((ROOT/'hardware/manifest.json').read_text())
    fir=Path('/scratch/eygao/iris-cy')/manifest['sources']['firesim-fir']['path']
    if sha(fir)!=manifest['sources']['firesim-fir']['sha256']:raise ValueError('FIR evidence changed')
    excerpt=[];inside=False;wire_count=0
    for number,line in enumerate(fir.open(),1):
        if line.startswith('  module ShuttleCore :'):inside=True;excerpt.append((number,line.rstrip()))
        elif inside and line.startswith('  module '):break
        if inside and ('wire rrd_uops :' in line or 'node rrd_p0_can_forward_x_to_m =' in line or
                       'node rrd_p0_can_forward_w_to_l =' in line):
            excerpt.append((number,line.rstrip()));wire_count+=1
    if wire_count!=3 or not any('}}[2]' in line for _,line in excerpt):raise ValueError('unexpected elaborated Shuttle issue dimensions')
    fir_snapshot=evidence/'fir-issue-excerpt.txt'
    fir_snapshot.write_text('\n'.join(f'{number}: {line}' for number,line in excerpt)+'\n')
    audit={'schema_version':1,'scope':'Iris source RRD issue selection and scalar control templates; not a complete timing model',
           'sources':entries,'generator_sha256':sha(Path(__file__)),'scalar_classes':CLASSES,'scalar_rows':len(rows),
           'decoder_header_sha256':sha(HERE/'shuttle_decode_rows.inc'),'rows':rows,'facts':facts(),
           'elaboration':{'full_file':str(fir),'full_sha256':sha(fir),'excerpt':str(fir_snapshot.relative_to(HERE)),
                          'excerpt_sha256':sha(fir_snapshot),'image_build_association':'unverified'},
           'unknown_timing_parameters':{'ALU_issue_to_commit_cycles':None,'branch_mispredict_cycles':None,
               'Icache_hit_miss_cycles':None,'scalar_load_store_cycles':None,'shared_resources_and_overlap':None},
           'rtl_certified':False,'accuracy_2_percent_certified':False}
    audit_path.write_text(json.dumps(audit,indent=2)+'\n')
    print(json.dumps({'status':'generated_source_bound_templates','scalar_rows':len(rows),'sources':len(entries),'rtl_certified':False}))


if __name__=='__main__':main()
