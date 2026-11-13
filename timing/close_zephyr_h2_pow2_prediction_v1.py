#!/usr/bin/env python3
"""Bind the completed fixed prediction and its finite independent controls."""
import json
from pathlib import Path
from replay_zephyr_h2_pow2_prediction_v1 import ROOT,sha,verify,need,PLAN_SHA


def main():
    prediction=ROOT/'build/zephyr-hart2-pow2-35a-OS-prediction-v1'
    run=json.loads((prediction/'run.json').read_text())
    freeze=json.loads((prediction/'freeze.json').read_text())
    need(run['pass'] is True and freeze['pass'] is True and run['timed_out'] is False
         and run['debugger_exit_status']==0, 'Complete controlled prediction')
    verify(run['input_sha256']);verify(run['output_sha256'])
    need(freeze['run_sha256']==sha(prediction/'run.json') and freeze['selected_plan_sha256']==PLAN_SHA
         and freeze['input_sha256']==run['input_sha256']
         and freeze['output_sha256']==run['output_sha256'], 'Exact prediction freeze consistency')
    need(run['actual_mcycle_endpoint_ELF_joins']==1944 and run['dynamic_minstret_prefix_joins']==0
         and run['RAM_minstret_pairs']==648 and run['complete_independent_elements']==181440,
         'Actual dynamic versus static/RAM counter scopes')
    guard=ROOT/'build/zephyr-hart2-pow2-prediction-guards-v1/report.json'
    g=json.loads(guard.read_text());need(g['pass'] is True and len(g['refusal_controls'])==16,'Finite parser controls')
    verify(g['input_sha256']);verify(g['source_sha256'])
    stepping=ROOT/'build/zephyr-firstuse-35a-OS-debugger-stepping-v1/report.json'
    s=json.loads(stepping.read_text());verify(s['input_sha256']);verify(s['output_sha256'])
    need(s['pass'] is True and s['exit_status']==0 and not s['timed_out']
         and s['stdout_bytes_equal'] is True and s['prefix_dictionary_equal'] is True
         and s['normal_prefixes']==s['debugger_prefixes']==248,'Finite normal/debugger control')
    audit=ROOT/'build/zephyr-hart2-pow2-independent-closure-v1/report.json'
    paths=[Path(__file__),prediction/'run.json',prediction/'freeze.json',guard,stepping,audit]
    report=dict(schema='iris.zephyr_pow2_fixed_prediction_delivery.v1',**{'pass':True},
                regions=648,independent_full_words=181440,guards=648,
                actual_dynamic_MCYCLE_ELF_endpoint_joins=1944,
                static_MINSTRET_ELF_sites=2,RAM_minstret_pairs=648,dynamic_MINSTRET_joins=0,
                source_plan_sha256=PLAN_SHA,prediction_freeze_sha256=sha(prediction/'freeze.json'),
                native_profile='fixed published 35a + source_os97ef; OPU/VADD source actors OFF',
                data_origin='initialized physical RAM readback at hart2 emit entry before all result UART',
                pre_post_terminal='done0/count648/PC80000844/actual initialized ELF code bytes unchanged',
                data_read_scope='18Q record, active initialized 8-byte chunks, two guards; no padding',
                raw_emit_bytes_hex='0571',raw_emit_little_endian_instruction_word='0x7105',
                parser_refusal_controls=16,
                debugger_stepping_control=dict(same_preserved_firstuse_ELF=True,normal_exit0=True,
                                              stdout_byte_equal=True,all248_prefix_dictionaries_equal=True),
                limitations=['Controlled debugger stop is not normal HTIF completion or E2E/simulation-speed qualification.',
                             'Finite first-use stepping parity does not prove universal SMP parity for the 648 packet.',
                             'MCYCLE may pause outside ROI; global endpoint edges come from actual prefix joins.',
                             'Mask3 can include worker/controller/readout memory contention; not isolated unit throughput.',
                             'FENCE instructions are observed; absolute VMU drain correctness is not newly certified.',
                             'No hardware timing labels, fitting, parameter/model selection, or source-image attestation.'],
                hardware_timing_labels_consumed=False,fit_performed=False,
                input_sha256={str(p):sha(p) for p in paths})
    out=ROOT/'build/zephyr-hart2-pow2-fixed-prediction-delivery-v1';out.mkdir(exist_ok=False)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    (out/'RUN.txt').write_text('python3 timing/replay_zephyr_h2_pow2_prediction_v1.py --output build/NEW-UNUSED-OUTPUT --timeout 900\n')
    print(json.dumps({'pass':True,'report_sha256':sha(out/'report.json')}))


if __name__=='__main__':main()
