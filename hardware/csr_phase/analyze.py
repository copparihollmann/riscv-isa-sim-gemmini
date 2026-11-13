#!/usr/bin/env python3
"""Check whole-CPU pre/post CSR transitions and their real RF writeback."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from iris_model.guest_regions import Instructions

MASK=(1<<64)-1
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def analyze(directory):
    run=json.loads((directory/'results.json').read_text())
    if run['exit_status']!=0 or run['timed_out'] is not False or run['changed_inputs'] or not run['full_signature_matches_unobserved_run']:
        raise ValueError('unaltered successful same-signature observer run required')
    for name,digest in run['artifact_sha256'].items():
        if sha(directory/name)!=digest:raise ValueError('changed phase artifact '+name)
    elf_digest=run['input_sha256'][run['argv'][-1]]
    archived_elf=directory/'inputs'/elf_digest
    if sha(archived_elf)!=elf_digest:raise ValueError('changed archived probe ELF')
    rows=json.loads((directory/'phase.json').read_text());image=Instructions(archived_elf)
    selected={hart:[] for hart in range(3)};writebacks=[]
    for row in rows:
        a,b=row['before'],row['after'];hart=row['hart']
        if a['inhibit'] or b['inhibit']:raise ValueError('probe unexpectedly inhibits counters')
        mc,ir=(a['mc']+1)&MASK,(a['ir']+a['retire'])&MASK
        csr=a['raw']>>20;is_counter=a['valid'] and (a['raw']&127)==0x73 and csr in (0xB00,0xB02)
        if is_counter:
            if image.read(a['pc'])!=a['raw'] or (a['raw']>>12)&7!=2 or (a['raw']>>15)&31 or a['retire']!=1:
                raise ValueError('unexpected observed counter instruction/retirement')
            expected=a['mc'] if csr==0xB00 else a['ir']
            if a['rdata']!=expected or a['cmd']!=(6 if hart<2 else 2):raise ValueError('source read-data/command mismatch')
            if hart<2:
                if csr==0xB00:mc=a['mc']
                else:ir=a['ir']
                if not(b['wb_valid'] and b['wb_data_valid'] and b['wb_wxd'] and b['wb_raw']==a['raw'] and b['wb_data']==a['rdata']):
                    raise ValueError('CSR COM result was not captured by WB')
            selected[hart].append(row)
        if (b['mc'],b['ir'])!=(mc,ir):raise ValueError('whole-CPU counter edge disagrees with source transition')
    for hart in (0,1):
        samples=[row for row in rows if row['hart']==hart]
        for read in selected[hart]:
            a=read['before'];rd=(a['raw']>>7)&31;register='x'+str(rd)
            following=[row for row in samples if row['counter_update_edge']==read['counter_update_edge']+1]
            if len(following)!=1:raise ValueError('missing next-edge RF observation')
            row=following[0];p,q=row['before'],row['after']
            if not(p['wb_valid'] and p['wb_wxd'] and p['wb_data_valid'] and p['wb_raw']==a['raw'] and
                   p['wb_data']==a['rdata'] and q[register]==a['rdata'] and row['time_ps']-read['time_ps']==2000):
                raise ValueError('Shuttle counter read did not reach actual RF one500MHz edge after COM')
            writebacks.append({'hart':hart,'pc':a['pc'],'raw':a['raw'],'value':a['rdata'],'destination':rd,
                               'read_time_ps':read['time_ps'],'rf_write_time_ps':row['time_ps'],
                               'counter_update_edge_distance':1})
    words=[int(line,16) for line in (directory/'signature').read_text().splitlines()]
    if len(words)!=56 or words[:8]!=[0x495249535343414c,1,0,1,1,1,0,0]:raise ValueError('failed/incomplete coherent probe signature')
    regions=[]
    for hart in range(3):
        reads=selected[hart]
        if len(reads)!=16:raise ValueError('all16 warm/measured CSR reads per hart are required')
        for index in range(4):
            group=reads[index*4:index*4+4]
            if [r['before']['raw']>>20 for r in group]!=[0xB00,0xB02,0xB02,0xB00]:raise ValueError('unexpected counter bracket sequence')
            begin_ir,end_ir=group[1]['before']['pc'],group[2]['before']['pc']
            registers=[]
            for pc in range(begin_ir+4,end_ir,4):
                raw=image.read(pc);rd=(raw>>7)&31;rs=(raw>>15)&31
                if raw&0x707f!=0x13 or raw>>20!=1 or rd!=rs or not rd:raise ValueError('body is not straight-line ADDI chains')
                registers.append(rd)
            if len(registers)!=256 or len(set(registers))!=(1 if index%2==0 else 8):raise ValueError('wrong body shape')
            if index<2:continue
            kind=index-2;record=words[8+hart*16+kind*8:16+hart*16+kind*8]
            values=[r['before']['rdata'] for r in group]
            if [record[0],record[2],record[3],record[1]]!=values:raise ValueError('coherent signature disagrees with exact CPU read data')
            if record[3]-record[2]!=(256 if hart<2 else 257):raise ValueError('source-specific visible minstret interval mismatch')
            regions.append({'hart':hart,'kernel':'dependent256' if kind==0 else 'independent256',
                            'mcycle_delta':record[1]-record[0],'visible_minstret_delta':record[3]-record[2],
                            'alu_body_retirements':256,'read_times_ps':[r['time_ps'] for r in group],
                            'mcycle_read_time_delta_core_edges':(group[-1]['time_ps']-group[0]['time_ps'])//2000})
    return {'sampled_counter_update_edges':len(rows),'counter_read_instructions':sum(map(len,selected.values())),
            'shuttle_rf_writebacks':writebacks,'regions':regions,
            'whole_cpu_source_counter_transitions_verified':True,'source_specific_probe_checks_passed':True,
            'original_strict_architectural_collector_status':'failed; untouched',
            'model_counter_policy_corrected':False,'absolute_model_read_phase_qualified':False}


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--verify',action='store_true');a=p.parse_args();directory=a.run.resolve();out=a.output.resolve()
    if a.verify:
        report=json.loads((out/'report.json').read_text())
        for name,digest in report['artifact_sha256'].items():
            if sha(out/name)!=digest:raise ValueError('changed frozen phase source/evidence '+name)
        # The frozen run is replayable independently of mutable live source paths.
        checked=analyze(out/'run')
        if checked!=report['analysis']:raise ValueError('phase analysis differs')
        print(json.dumps({'verified':True,'counter_reads':checked['counter_read_instructions'],'hardware_contacted':False}));return
    checked=analyze(directory);out.mkdir(parents=True,exist_ok=False);shutil.copytree(directory,out/'run')
    extra=[Path(__file__),ROOT/'hardware/csr_phase/build.py',ROOT/'hardware/csr_phase/run.py',
           ROOT/'iris_model/guest_regions.py',ROOT/'iris_model/counter_regions.py',ROOT/'iris_model/report.py',
           ROOT/'build/pipeline-csr-proof-closed/manifest.json',ROOT/'hardware/manifest.json']
    (out/'sources').mkdir();origins={}
    for path in extra:
        digest=sha(path);(out/'sources'/digest).write_bytes(path.read_bytes());origins[str(path)]=digest
    report={'schema':'iris.whole_cpu_counter_phase_proof.v1','analysis':checked,'source_input_sha256':origins,
            'hardware_contacted':False,'rtl_design_changed':False,'timing_calibrated':False,'ethan_image_association_verified':False,
            'limitations':['Read-only observer of two-state standalone native-memory RTL, not attested deployed image.',
                           'All observed writable-counter reads use CSRRS with encoded rs1=x0; other forms have independent unit coverage.',
                           'The model COM tick convention still needs an explicit implementation and comparison.',
                           'Original strict collector failure and historical native packages remain unchanged.']}
    report['artifact_sha256']={str(path.relative_to(out)):sha(path) for path in out.rglob('*') if path.is_file()}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'report.json')


if __name__=='__main__':main()
