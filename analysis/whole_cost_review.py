"""Private, reproducible analysis of admitted convolution phases and shape costs."""
import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

A = Path('/users/copparihollmann/iris-work/out/artifacts/probes/utilization-correction-v1/approved-operator-campaign-20261110-v1')
COST = Path('/scratch/copparihollmann/iris-mlir-direct-conv-pack/src/iris/transforms/offload_costs.py')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(p):
    return json.loads(Path(p).read_text())


def main(out):
    out.mkdir(parents=True, exist_ok=False)
    paths = dict(conv=A/'corrected-boundary-matched168-20261111-v1/regular-load-analysis-v2/report.json',
                 conv_gate=A/'corrected-boundary-matched168-20261111-v1/runs/matched168-v1/archive-admission/report.json',
                 memory=A/'memory-roofline-20261111-v1/achievable-efficiency-reference.json',
                 memory_gate=A/'memory-roofline-20261111-v1/target-admission-v4/report.json',
                 shape_catalog=A/'analytic-shape-screen-v1/report.json', cost_module=COST,
                 source=Path(__file__).resolve())
    snapshots = out/'evidence-snapshots'
    snapshots.mkdir()
    for p in paths.values():
        payload = Path(p).read_bytes()
        (snapshots/hashlib.sha256(payload).hexdigest()).write_bytes(payload)
    data = load(paths['conv'])
    if (not load(paths['conv_gate'])['pass_'] or not load(paths['memory_gate'])['pass_']
            or sha(paths['conv_gate']) != data['admission_sha256']
            or sha(data['CSV']) != data['CSV_sha256'] or data['accepted_trials'] != 168):
        raise ValueError('Missing or changed admitted evidence')
    spec = importlib.util.spec_from_file_location('private_offload_cost', COST)
    cost = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = cost
    spec.loader.exec_module(cost)
    catalog = load(paths['shape_catalog'])
    hw = cost.Geometry(256, 128, 32, 32, 2, 524288, 131072, str(paths['shape_catalog']))
    features = []
    for case in catalog['cases']:
        p = case['parameters']
        if case['operator'] == 'gemm':
            ops = dict(gemm=cost.Contraction(p['M'], p['N'], p['K']))
        elif case['operator'] == 'conv':
            ops = dict(conv=cost.convolution(p['B'], p['Cin'], p['Cout'], p['H'], p['W'], p['R'], p['S'],
                       p['stride'], p['padding'], p['dilation'], p['groups']))
        else:
            attn = cost.attention(p['B'], p['Lq'], p['Lkv'], p['Hq'], p['Hkv'], p['D'])
            ops = {k: attn[k] for k in ('QK', 'PV')}
        features.append(dict(case_id=case['case_id'], operator=case['operator'],
                             predictions={k: cost.features(v, hw) for k, v in ops.items()},
                             timings_predicted=False, routing_recommendation=None,
                             precision_scope='INT8 contraction features; FP8 quality qualification separate'))
    (out/'shape-features.json').write_text(json.dumps(features, indent=2)+'\n')
    rows = data['all_rows']
    if len(rows) != 168 or len({(r['point'], r['route'], r['pass_id']) for r in rows}) != 168:
        raise ValueError('Incomplete or duplicated convolution observations')
    summaries, comparisons = [], []
    for summary in data['summary']:
        point = summary['point']
        pair = []
        for kind in ('RVV', 'VME'):
            name = summary[f'best_{kind}_route']
            selected = sorted((r for r in rows if int(r['point']) == point and r['route_name'] == name), key=lambda r: int(r['pass_id']))
            if [int(r['pass_id']) for r in selected] != [0, 1, 2]:
                raise ValueError('Three ordered repetitions required')
            third = selected[2]
            parts = {k: int(third[k+'_ticks']) for k in ('quant', 'prepare', 'worker', 'finish')}
            whole = int(third['whole_ticks'])
            parts['dispatch_sync_timer_residual'] = whole - sum(parts.values())
            if min(parts.values()) < 0:
                raise ValueError('Non-partitioning timing windows; do not fabricate a residual')
            cycles = int(third['whole_h0_cycles'])
            record = dict(point=point, shape=summary['shape'], parameters=summary['parameters'],
                          held_out_from_fitting=summary['held_out_from_fitting'], route=name, kind=kind,
                          first_ordered_ticks=int(selected[0]['whole_ticks']),
                          second_ordered_ticks=int(selected[1]['whole_ticks']), third_ordered_ticks=whole,
                          ordered_min_ticks=min(int(r['whole_ticks']) for r in selected),
                          ordered_max_ticks=max(int(r['whole_ticks']) for r in selected),
                          ordered_spread_over_third=(max(int(r['whole_ticks']) for r in selected)-min(int(r['whole_ticks']) for r in selected))/whole,
                          whole_h0_cycles=cycles, nominal_convolution_MACs=int(third['useful_macs']),
                          nominal_MACs_per_H0_observed_cycle=int(third['useful_macs'])/cycles,
                          phase_ticks=parts, phase_fractions={k: v/whole for k, v in parts.items()},
                          hypothetical_max_speedup_if_worker_free=whole/(whole-parts['worker']),
                          route_selection='posthoc best third pass among tested candidates, not heldout policy validation',
                          cache_cold_certified=False, physical_busy=None)
            if kind == 'VME':
                record['effective_fraction_source256_MAC_per_cycle'] = int(third['useful_macs'])/(256*cycles)
            pair.append(record)
            summaries.append(record)
        rvv, vme = pair
        comparisons.append(dict(point=point, parameters=summary['parameters'],
                                whole_VME_speedup=rvv['third_ordered_ticks']/vme['third_ordered_ticks'],
                                worker_window_VME_speedup=rvv['phase_ticks']['worker']/vme['phase_ticks']['worker'],
                                VME_preparation_fraction=vme['phase_fractions']['prepare'],
                                VME_finish_fraction=vme['phase_fractions']['finish'],
                                VME_effective_capacity_fraction=vme['effective_fraction_source256_MAC_per_cycle']))
    with (out/'conv-comparisons.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[k for k in comparisons[0] if k != 'parameters'])
        writer.writeheader()
        for row in comparisons:
            writer.writerow({k: v for k, v in row.items() if k != 'parameters'})
    labels = []
    for s in data['summary']:
        p=s['parameters'];labels.append(f"H{p['H']}\ns{p['stride']} g{p['groups']}")
    fig, axes = plt.subplots(1, 2, figsize=(15, 6), constrained_layout=True)
    x=np.arange(len(labels)); colors=['#72b7b2','#eeca3b','#4c78a8','#f58518','#b279a2']
    phase_labels=['Quantization','Preparation','Worker callback','Output finish','Dispatch/sync/timer residual']
    for ax, kind in zip(axes, ('RVV','VME')):
        subset=[r for r in summaries if r['kind']==kind];bottom=np.zeros(len(subset))
        for j,key in enumerate(subset[0]['phase_fractions']):
            values=np.array([r['phase_fractions'][key] for r in subset])*100
            ax.bar(x,values,bottom=bottom,color=colors[j],label=phase_labels[j]);bottom+=values
        ax.set(xticks=x,xticklabels=labels,ylim=(0,100),ylabel='Whole-operation time (%)',title=f'{kind}: best tested route at each shape')
    axes[0].legend(fontsize=8,loc='upper center',bbox_to_anchor=(0.5,-0.17),ncol=3)
    fig.suptitle('Convolution: where whole-operation time goes\nThird ordered pass · H0 compute, H2 preparation/control · no physical-busy measurement')
    for ext in ('png','svg'):fig.savefig(out/f'conv-whole-operation-phases.{ext}',dpi=160,bbox_inches='tight')
    plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(15,5),constrained_layout=True)
    axes[0].bar(x-.17,[r['whole_VME_speedup'] for r in comparisons],.34,label='Whole operation')
    axes[0].bar(x+.17,[r['worker_window_VME_speedup'] for r in comparisons],.34,label='Worker callback')
    axes[0].axhline(1,color='black',linewidth=.8);axes[0].set(xticks=x,xticklabels=labels,ylabel='RVV time / VME time',title='Compute-window gains do not equal whole-operation gains');axes[0].legend()
    axes[1].bar(x,[100*r['VME_effective_capacity_fraction'] for r in comparisons],color='#f58518')
    axes[1].set(xticks=x,xticklabels=labels,ylabel='Nominal conv MACs / (256 × whole H0 cycles), %',title='Effective VME capacity efficiency, not physical busy')
    fig.suptitle('Matched INT8 convolution · 7 shapes, 8 tested routes, 168 accepted observations')
    for ext in ('png','svg'):fig.savefig(out/f'conv-whole-versus-worker.{ext}',dpi=160,bbox_inches='tight')
    plt.close(fig)
    report=dict(schema='iris.private.whole_cost_review.v1', accepted_conv_observations=168,
                accepted_memory_observations=432, shape_feature_cases=len(features),
                comparisons=comparisons, selected_route_breakdowns=summaries,
                memory_interpretation=load(paths['memory']),
                recommendation='Test reduced runtime preparation and output movement before assuming more compute throughput helps.',
                automatic_policy_changed=False, FPGA_measurements_fitted=False,
                physical_busy=None, unit_note='Phase breakdowns use shared mtime ticks. Whole H0 cycles are recorded separately; no inferred tick-to-cycle conversion.',
                selection_caveat='Best tested route chosen on these data. This is exploratory comparison, not independent generalization validation.',
                causal_attention_caveat='Dense QK and PV contractions counted; causal triangle skipping and softmax/quantization costs are not assumed absent.',
                convolution_MAC_scope='Nominal dense zero-extended convolution work; implementations may skip padding-zero multiplies. This is not a count of executed MAC instructions.',
                evidence_sha256={str(p):sha(p) for p in paths.values()})
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('comparisons','selected_route_breakdowns','memory_interpretation','evidence_sha256')}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--output',type=Path,required=True)
    main(parser.parse_args().output.resolve())
