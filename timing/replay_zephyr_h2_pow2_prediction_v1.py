#!/usr/bin/env python3
"""Fixed 35a/OS prediction: initialized RAM at the final pre-UART emit PC.

Debugger step(1) is a controlled measurement execution, not normal HTIF exit
or an assertion of scheduling parity with normal step(INTERLEAVE).
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from iris_model.guest_regions import Instructions
sys.path.insert(0, str(ROOT / 'timing'))
from audit_zephyr_h2_pow2_independent_v4 import ELF, bodies, golden, fnv

ELF_SHA = 'd47bec0012e4beea0df17b8f1d1c0aa0dc53f07f2a2dc9e8ed0fd5b5bbb49430'
LAYOUT_SHA = '25845837f268b73affce5292af1b45b1d45f00df6a9de68cdc685d18b3c9c88c'
READY_SHA = '7fb5667d0eb233cfbed930257fc8ad732c8bbfb0653452205f2c43287e91f994'
PLAN_SHA = '26a690b032aab3663d431ed4aad6f57105297c8abd45722ac8a4675276138706'
CAPSULE_SHA = '11bb432849e733743ee9fb271110c303264710771ff59913cb0d3a4a6ed354df'
FIXTURE_SHA = '97ef45bb2cfb7144a1798e594df8065a55989980c8b406d0fe1e221597ef1bcb'
GUARD = 0x5ac31e79a64db208
FIELDS = 'rid gid hart logical pin start issued end ir0 ir1 elements failed checksum actual_vl rows cols guard_ok ack'.split()
CSR_SITES = (0x80000342, 0x8000034e, 0x80000356)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def need(ok, why):
    if not ok:
        raise ValueError(why)


def verify(bindings):
    for path, digest in bindings.items():
        need(sha(path) == digest, 'Changed bound bytes: ' + str(path))


def inputs():
    source = ROOT / 'benchmarks/zephyr_hart2_pow2_v4'
    ready_path = ROOT / 'build/zephyr-hart2-pow2-qualified-v1/ready.json'
    layout_path = ROOT / 'build/zephyr-hart2-pow2-ELF-layout-v1/layout.json'
    plan = ROOT / 'build/zephyr-pow2-35a-OS-selection-v1/plan.json'
    capsule = ROOT / 'build/C12-VADD-EG-frozen-35a80496-v2'
    fixture = ROOT / 'build/C12-source-composite-inputs-v1/fixed-costs-OPU-OFF.fixture'
    fixed = {ready_path: READY_SHA, layout_path: LAYOUT_SHA, plan: PLAN_SHA,
             capsule / 'manifest.json': CAPSULE_SHA, fixture: FIXTURE_SHA}
    verify(fixed)
    ready, layout = [json.loads(p.read_text()) for p in (ready_path, layout_path)]
    for pathkey, hashkey in [('elf','elf_sha256'), ('build','build_sha256'),
                             ('corpus_path','corpus_sha256'), ('split_path','split_sha256'),
                             ('qualification','qualification_sha256')]:
        verify({ready[pathkey]: ready[hashkey]})
        fixed[Path(ready[pathkey])] = ready[hashkey]
    qualification = json.loads(Path(ready['qualification']).read_text())
    verify(qualification['input_sha256'])
    fixed.update({Path(p): d for p,d in qualification['input_sha256'].items()})
    verify(layout['input_sha256'])
    fixed.update({Path(p): d for p,d in layout['input_sha256'].items()})
    manifest = json.loads((capsule / 'manifest.json').read_text())
    for name, digest in manifest['artifact_sha256'].items():
        p = capsule / name
        verify({p: digest})
        fixed[p] = digest
    elf = Path(ready['elf'])
    need(sha(elf) == ELF_SHA == layout['ELF_sha256'], 'Exact final ELF')
    corpus = json.loads((source / 'corpus.json').read_text())
    need(len(corpus['regions']) == len(layout['regions']) == 648, 'Exact 648 geometry')
    binary = ELF(elf.read_bytes())
    bodies(binary)
    stop = layout['postmeasurement_stop']
    need(stop['pc'] == binary.symbols['emit'][0] == 0x80000844
         and binary.memory(stop['pc'], 2) == bytes.fromhex('0571'), 'Compiled pre-UART emit stop bytes')
    need(layout['DWARF_types']['record_t']['bytes'] == 144
         and [f['name'] for f in layout['DWARF_types']['record_t']['fields']] == FIELDS,
         'Exact initialized 18Q record layout')
    descs = list(struct.iter_unpack('<6I', binary.raw('descriptors')))
    record_base = binary.symbols['records'][0]
    output_base = binary.symbols['output_data'][0]
    for i, (row, item, desc) in enumerate(zip(corpus['regions'], layout['regions'], descs)):
        need(desc == (row['group'], row['hart'], row['offset'], row['bytes'],
                      row['elements'], row['element_bytes']), 'Compiled descriptor')
        need(item['region_index'] == i and item['record_address'] == record_base + 144*i
             and item['active_data_address'] == output_base + row['offset'] + 8
             and item['active_bytes'] == row['bytes'] and item['active_bytes'] % 8 == 0
             and item['leading_guard_address'] == output_base + row['offset']
             and item['trailing_guard_address'] == output_base + row['offset'] + 8 + row['bytes']
             and item['guard_value'] == GUARD, 'Initialized-only readback geometry')
    for p in [Path(__file__), ROOT/'timing/audit_zephyr_h2_pow2_independent_v4.py',
              ROOT/'iris_model/guest_regions.py', ROOT/'spike/empirical_launch_v2.py',
              ROOT/'zephyr/hart2_pow2_validate_v4.py', source/'cases.py',
              ROOT/'board/evidence/bootrom.rv64.img', ROOT/'board/build/iris.dtb']:
        fixed[p] = sha(p)
    return corpus, layout, binary, elf, capsule, fixture, {str(p):d for p,d in fixed.items()}


def commands(layout):
    stop = layout['postmeasurement_stop']
    snapshot = [f'mem {stop["done_address"]:x}', f'mem {stop["count_address"]:x}',
                'pc 2', f'mem {stop["pc"] & ~7:x}']
    result = ['rs 0', f'until pc 2 {stop["pc"]:x}'] + snapshot
    for item in layout['regions']:
        result += [f'mem {item["record_address"]+8*j:x}' for j in range(18)]
        result += [f'mem {item["active_data_address"]+j:x}' for j in range(0,item['active_bytes'],8)]
        result += [f'mem {item[key]:x}' for key in ('leading_guard_address','trailing_guard_address')]
    return result + snapshot + ['quit']


def decode(text, corpus, layout, binary):
    lines = text.splitlines()
    need(lines and lines[0] == ':' and all(re.fullmatch('0x[0-9a-f]{16}', s)
         for s in lines[1:]), 'Exact debugger scalar-value stream')
    values = [int(s,16) for s in lines[1:]]
    count = 8 + sum(20 + item['active_bytes']//8 for item in layout['regions'])
    need(len(values) == count, 'Complete initialized record/output/guard readback')
    stop = layout['postmeasurement_stop']
    code = int.from_bytes(binary.memory(stop['pc'] & ~7,8),'little')
    wanted = [0,648,0x80000844,code]
    need(values[:4] == values[-4:] == wanted, 'Stable pre/post done/count/PC/actual code')
    pos, total, acks, rows = 4, 0, [0,0], []
    bytehash = hashlib.sha256()
    for expected, item in zip(corpus['regions'], layout['regions']):
        record = dict(zip(FIELDS,values[pos:pos+18]));pos += 18
        qwords = item['active_bytes']//8
        raw = b''.join(v.to_bytes(8,'little') for v in values[pos:pos+qwords]);pos += qwords
        guards = values[pos:pos+2];pos += 2
        h = expected['hart']; acks[h] += 1
        want_fields = dict(rid=expected['region_index'],gid=expected['group'],hart=h,logical=h,pin=h,
                           elements=expected['elements'],failed=0,actual_vl=expected['elements']
                           if not expected['kind'] else expected['shape'],guard_ok=1,ack=acks[h],
                           rows=1 if not expected['kind'] else expected['shape'],
                           cols=expected['elements'] if not expected['kind'] else expected['shape'])
        need(all(record[k] == v for k,v in want_fields.items()), 'Actual record identity/configuration/goldens')
        need(record['start'] < record['issued'] <= record['end'] and record['ir0'] < record['ir1'],
             'Actual ordered cycle and RAM instruction counters')
        width = expected['element_bytes']
        words = [int.from_bytes(raw[j:j+width],'little') for j in range(0,len(raw),width)]
        need(words == golden(expected) and record['checksum'] == fnv(words), 'Independent every-element golden/checksum')
        need(guards == [GUARD,GUARD], 'Both actual output guards')
        total += len(words);bytehash.update(raw)
        rows.append(dict(expected, start_cycle=record['start'],issue_cycle=record['issued'],
                         end_cycle=record['end'],cycles=record['end']-record['start'],
                         issue_cycles=record['issued']-record['start'],
                         drain_cycles=record['end']-record['issued'],
                         RAM_minstret_before=record['ir0'],RAM_minstret_after=record['ir1'],
                         instret_delta=record['ir1']-record['ir0'],checksum=record['checksum'],
                         guard_ok=True,ack=record['ack'],data_origin='controlled_initialized_RAM_readback'))
    need(pos == len(values)-4 and total == 181440 and acks == [324,324], 'Complete all-element coverage')
    return rows, bytehash.hexdigest()


def qualify_prefix(path, rows, elf, rom):
    raw = path.read_bytes()
    need(raw.endswith(b'\n'), 'Flushed actual prefix')
    code, previous, lookup, identities = Instructions(elf,rom), {}, {}, set()
    prefixes = [json.loads(line) for line in raw.splitlines()]
    for event in prefixes:
        h, seq = event['hart'], event['sequence']
        need(type(h) is int and h in (0,1,2) and type(seq) is int and seq > previous.get(h,-1), 'Ordered actual prefix ownership')
        previous[h] = seq
        for k in ('value','read_cycle','pc','raw','csr','destination'):
            need(type(event[k]) is int and event[k] >= 0, 'Typed actual prefix field')
        word = event['raw']
        need(word == code.read(event['pc']) and word & 127 == 0x73 and word >> 20 in (0xb00,0xc00)
             and event['csr'] == word >> 20 and event['destination'] == (word >> 7)&31,
             'Executed returning MCYCLE instruction from actual ELF/ROM')
        identities.add(event['calibration_identity'])
        if event['pc'] in CSR_SITES:
            key = h,event['pc'],event['value']
            need(key not in lookup and event['result_discarded'] is False, 'Unique returning measured endpoint')
            lookup[key] = event
    need(len(lookup) == 1944 and len(identities) == 1, 'Exactly 1944 dynamic measured MCYCLE joins')
    for row in rows:
        endpoints = [lookup.pop((row['hart'],pc,row[k])) for pc,k in zip(CSR_SITES,('start_cycle','issue_cycle','end_cycle'))]
        need(endpoints[0]['sequence'] < endpoints[1]['sequence'] < endpoints[2]['sequence']
             and endpoints[0]['read_cycle'] < endpoints[1]['read_cycle'] <= endpoints[2]['read_cycle'], 'Actual CSR global phase order')
        for label,event in zip(('begin','issue','drain'),endpoints):
            row[label+'_pc'] = event['pc'];row[label+'_global_read_cycle'] = event['read_cycle']
            row[label+'_prefix_sequence'] = event['sequence']
    need(not lookup, 'Every measured actual event consumed exactly once')
    return next(iter(identities)),len(prefixes)


def main(args):
    corpus,layout,binary,elf,capsule,fixture,bindings = inputs()
    need(0 < args.timeout <= 900, 'Owned positive timeout at most 900 seconds')
    out = args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    (out/'commands.txt').write_text('\n'.join(commands(layout))+'\n')
    bindings[str(out/'commands.txt')] = sha(out/'commands.txt')
    rom,dtb = ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb'
    dma='rv64gcv_zfh_zvfh_zvl256b_zvbb'
    compute='rv64gcv_zfh_zvfh_zba_zbb_zbs_zvbb_zvl256b_zvfofp8min_zvfbfmin_zvfbfa_zvt32t_zvti8i32mm_zvtofp8fmm'
    argv=[str(capsule/'spike'),'-d','--debug-cmd='+str(out/'commands.txt'),
          '--iris-timing-fixture='+str(fixture),'--iris-timing-trace='+str(out/'native-summary.json'),
          '--extlib='+str(capsule/'libsifive_uart.so'),'--iris-vme','--isa='+dma,
          '--hart-isa=0:'+compute,'--hart-isa=1:'+compute,'--hart-isa=2:'+dma,'-p3',
          '-m0x70000000:0x40000,0x80000000:0x100000000,0x580000000:0x20000',
          '--device=sifive_uart,0x10020000','--iris-bootrom='+str(rom),'--dtb='+str(dtb),
          '--iris-schedule-seed=0',str(elf)]
    helper_path=ROOT/'spike/empirical_launch_v2.py'
    spec=importlib.util.spec_from_file_location('zephyr_prediction_fatal',helper_path)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    env={k:v for k,v in os.environ.items() if not k.startswith('IRIS_EMPIRICAL_') and k!='IRIS_FATAL_PCS'}
    env['IRIS_EMPIRICAL_FEATURES']=str(out/'features.jsonl')
    env['IRIS_FATAL_PCS']=','.join(hex(v) for v in sorted(set(helper.fatal_addresses(elf).values())))
    report=dict(schema='iris.zephyr_pow2_fixed_model_prediction.v1',status='running',argv=argv,
                input_sha256=bindings,normal_guest_exit_verified=False,
                intentional_postmeasurement_debugger_stop=True,whole_run_timing_or_speed_claim=False,
                debugger_step1_equals_normal_interleave_claim=False,hardware_contacted=False,
                hardware_timing_labels_consumed=False,fit_performed=False,
                selected_plan_sha256=PLAN_SHA,fixture_sha256=FIXTURE_SHA,capsule_manifest_sha256=CAPSULE_SHA)
    def save(): (out/'run.json').write_text(json.dumps(report,indent=2)+'\n')
    save();started=time.monotonic()
    with (out/'stdout').open('w') as stdout,(out/'stderr').open('w') as stderr:
        process=subprocess.Popen(argv,stdout=stdout,stderr=stderr,env=env,start_new_session=True)
        report['owned_process_group']=process.pid;save()
        try: report['debugger_exit_status']=process.wait(timeout=args.timeout);report['timed_out']=False
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGTERM)
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired: os.killpg(process.pid,signal.SIGKILL);process.wait()
            report.update(debugger_exit_status=process.returncode,timed_out=True)
    report['host_seconds']=time.monotonic()-started
    try:
        need(report['debugger_exit_status']==0 and not report['timed_out'],'Complete owned model execution/readback')
        rows, data_sha=decode((out/'stderr').read_text(),corpus,layout,binary)
        identity,prefixes=qualify_prefix(out/'features.jsonl',rows,elf,rom)
        need([l.split()[2] for l in fixture.read_text().splitlines() if l.startswith('empirical_profile ')]==[identity], 'Executed fixed fixture identity')
        verify(bindings)
        (out/'regions.jsonl').write_text(''.join(json.dumps(row,sort_keys=True)+'\n' for row in rows))
        report.update(status='completed_all648_at_pre_UART_emit',**{'pass':True},regions=648,
                      complete_independent_elements=181440,guard_regions=648,
                      actual_mcycle_endpoint_ELF_joins=1944,total_mcycle_prefix_records=prefixes,
                      static_minstret_sites=[0x80000346,0x8000035a],
                      dynamic_minstret_prefix_joins=0,RAM_minstret_pairs=648,
                      active_output_bytes_sha256=data_sha,calibration_identity=identity)
    except (ValueError,KeyError,OSError,TypeError,AssertionError) as error:
        report.update(status='failed',**{'pass':False},error=str(error))
    report['output_sha256']={str(p):sha(p) for p in out.iterdir() if p.name in
                            ('stdout','stderr','features.jsonl','native-summary.json','regions.jsonl')}
    save()
    if report['pass']:
        freeze=dict(schema='iris.zephyr_pow2_fixed_prediction_freeze.v1',**{'pass':True},
                    frozen_at_utc=datetime.now(timezone.utc).isoformat(),
                    selected_plan_sha256=PLAN_SHA,run_sha256=sha(out/'run.json'),
                    input_sha256=bindings,output_sha256=report['output_sha256'],
                    hardware_timing_labels_consumed=False,fitting_permitted=False,
                    normal_HTIF_or_E2E_claim=False,debugger_vs_normal_SMP_parity_claim=False)
        (out/'freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    print(json.dumps({k:report.get(k) for k in ('pass','status','regions','host_seconds','error')}))
    return 0 if report['pass'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--timeout',type=float,default=900)
    raise SystemExit(main(p.parse_args()))
