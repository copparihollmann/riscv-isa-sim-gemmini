"""Read-only, source-ceiling overlay for a qualified full-history VME execution.

This compares completed *logical model work* with conditional source capacities.
It intentionally cannot produce physical OPU utilization or a DRAM roofline.
"""
import argparse
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = "0b9ddd00e1763067f7540ffaa958ba0b0c8db648309fad8005c5511815bb6a91"
PROFILE_SHA = "404881caaedd37944f8812f297678fba71923f77d4d22c5cbf888a0b5f92288b"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name}: exact integer >= {minimum} required")
    return value


def flag(record, name, default=False):
    value = record.get(name, default)
    if type(value) is not bool:
        raise ValueError(f"{name}: exact boolean required")
    return value


def clock_edges(start, end, divider, phase=0):
    """Potential source edges at phase+n*divider in the half-open window."""
    integer(start, "start"); integer(end, "end"); integer(divider, "divider", 1)
    integer(phase, "phase")
    if end <= start or phase >= divider:
        raise ValueError("Nonempty window and normalized clock phase required")
    return (end - 1 - phase) // divider - (start - 1 - phase) // divider


def capacity(records, hart, family):
    integer(hart, "hart")
    if hart not in (0, 1, 2) or family not in ("vme.int8", "vme.fp8"):
        raise ValueError("Configured hart and exact MAC family required")
    candidates = [r for r in records if r.get("hart") == hart and r.get("family") == family]
    if len(candidates) > 1:
        raise ValueError("Duplicate capacity is not additive")
    if not candidates:
        if hart == 2:
            return None
        raise ValueError("Configured compute OPU capacity missing")
    record = candidates[0]
    if hart == 2:
        raise ValueError("This configured Rocket has no VME OPU")
    integer(record.get("value"), "capacity", 1)
    if (record.get("units") != "cell_MACs/accepted_array_edge" or
            record.get("kind") != "conditional_source_capacity_upper_bound" or
            record.get("arithmetic_ops_per_mac") != 2 or
            not isinstance(record.get("conditions"), list) or not record["conditions"]):
        raise ValueError("Exact conditional MAC units and source conditions required")
    return record


def delta(before, after):
    result = {}
    for family in before.keys() | after.keys():
        b, a = before.get(family, {}), after.get(family, {})
        if not isinstance(b, dict) or not isinstance(a, dict):
            raise ValueError("Counter family object required")
        result[family] = {}
        for key in b.keys() | a.keys():
            bv, av = integer(b.get(key, 0), key), integer(a.get(key, 0), key)
            if av < bv:
                raise ValueError("Cumulative feature counter decreased")
            result[family][key] = av - bv
    return result


def byte_coordinates(features, memory, macs):
    """Keep retired data requests, accepted intent requests and VRF moves apart."""
    integer(macs, "logical MACs")
    for table in (features, memory):
        for value in table.values():
            integer(value.get('bytes', 0), 'per-family requested bytes')
    architectural = sum(v.get("bytes", 0) for k, v in features.items() if k.startswith("memory."))
    intents = sum(v.get("bytes", 0) for k, v in memory.items() if not k.startswith("ICACHE."))
    for v in (architectural, intents):
        integer(v, "requested bytes")
    return {
        "retired_instruction_requested_data_bytes": architectural,
        "accepted_timing_intent_requested_data_bytes": intents,
        "retired_VRF_row_move_bytes_excluded_from_data_denominator": features.get("vme.row_move", {}).get("bytes", 0),
        "instruction_fetch_requested_bytes_excluded_from_data_denominator": sum(v.get("bytes", 0) for k, v in memory.items() if k.startswith("ICACHE.")),
        "architectural_MACs_per_requested_data_byte": macs / architectural if architectural else None,
        "logical_MACs_per_accepted_intent_requested_byte": macs / intents if intents else None,
        "physical_DRAM_bytes": None, "physical_L2_bytes": None,
        "physical_arithmetic_intensity": None,
    }


def work_completion(events, hart, start, end):
    credited, excluded, unresolved = [], [], []
    for event in events:
        if event.get("hart") != hart:
            continue
        macs = integer(event.get("macs", 0), "event MAC payload")
        if not macs:
            continue
        begin, finish = integer(event.get("start"), "event start"), integer(event.get("end"), "event end")
        if finish < begin:
            raise ValueError("Negative event span")
        canceled = flag(event, "cancelled")
        squashed = flag(event, "squashed")
        done = flag(event, "completed")
        issued = flag(event, "issued", True)
        if canceled and done:
            raise ValueError("Canceled operation cannot also be completed")
        if done and not issued:
            raise ValueError('Completed work must have issued')
        # Zero-duration canceled requests still intersect their cancellation edge.
        overlaps = (begin < end and finish > start) or (start <= begin < end and begin == finish)
        if not overlaps:
            continue
        evidence = {k: event.get(k) for k in ("id", "pc", "name", "resource", "start", "end", "macs")}
        if canceled or squashed:
            evidence.update(cancelled=canceled, squashed=squashed)
            excluded.append(evidence)
        elif done and issued and start <= begin < finish < end:
            credited.append(evidence)
        else:
            unresolved.append(evidence)
    return {
        "completed_logical_MACs": sum(e["macs"] for e in credited),
        "credited_operations": credited,
        "excluded_canceled_or_squashed_operations": excluded,
        "boundary_or_pending_MAC_payloads": unresolved,
        "model_completion_window_qualified": not unresolved,
        "completion_basis": "uncanceled, unsquashed model actors with start>=ROI start and end<ROI end; independently matched to retired MAC features and algorithm",
        "physical_MAC_completion_verified": False,
    }


def conditional_fraction(macs, edge_count, peak, qualified):
    integer(macs, "MACs"); integer(edge_count, "source edge opportunities")
    if type(qualified) is not bool:
        raise ValueError("Typed completion qualification required")
    if peak is None:
        return {"fraction": None, "inconsistency": macs != 0, "reason": "no configured VME OPU"}
    integer(peak, "MAC/edge capacity", 1)
    if not qualified or not edge_count:
        return {"fraction": None, "inconsistency": False, "reason": "completion or source-edge window unqualified"}
    fraction = macs / (peak * edge_count)
    return {"fraction": fraction, "inconsistency": fraction > 1,
            "reason": "logical work exceeds conditional ceiling" if fraction > 1 else None}


def verify_map(mapping, collected, base=None):
    for name, expected in mapping.items():
        path = Path(name)
        if not path.is_absolute():
            path = (base or ROOT) / path
        if sha(path) != expected:
            raise ValueError(f"Source/evidence digest mismatch: {path}")
        collected[str(path.resolve())] = expected


def render_svg(regions):
    lines = ['<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="510" viewBox="0 0 1120 510">',
             '<rect width="1120" height="510" fill="white"/>',
             '<g font-family="sans-serif" fill="#172337">',
             '<text x="30" y="30" font-size="20">Logical VME work versus conditional source capacity</text>',
             '<text x="30" y="55" font-size="13">Actual ELF; captured model CSR windows. Potential core edges, not observed physical OPU activity.</text>',
             '<text x="30" y="80" font-size="13">Format and hart share one selected 256-MAC/accepted-array-edge ceiling; no peaks are summed.</text>',
             '<text x="30" y="115" font-size="14">ROI / hart</text><text x="330" y="115" font-size="14">Conditional fraction of source ceiling</text>',
             '<text x="800" y="115" font-size="14">MAC/requested byte</text>']
    for i, r in enumerate(regions):
        y = 153 + i * 44
        f = r['conditional_source_peak_fraction']['fraction']
        intensity = r['byte_coordinates']['architectural_MACs_per_requested_data_byte']
        label = r['region'].split('::')[0].replace('profile.source.VME.', '') + f" / h{r['hart']}"
        lines.append(f'<text x="30" y="{y}" font-size="14">{html.escape(label)}</text>')
        if f is None:
            lines.append(f'<text x="330" y="{y}" font-size="14">N/A: no VME OPU on hart2</text>')
        else:
            # Numerical value remains unbounded in JSON and text; do not clamp.
            lines.append(f'<rect x="330" y="{y-16}" width="{f*400:.4f}" height="20" fill="#2f75b5"/>')
            lines.append(f'<text x="{max(370,340+f*400):.3f}" y="{y}" font-size="14">{100*f:.4f}%</text>')
        lines.append(f'<text x="800" y="{y}" font-size="14">{intensity:.6f}</text>' if intensity is not None else f'<text x="800" y="{y}">unknown</text>')
    lines.extend(['<text x="30" y="445" font-size="13">Region-local requested-data intensity excludes operand setup, VRF row moves and instruction fetch.</text>',
                  '<text x="30" y="468" font-size="13">Physical DRAM/L2 traffic, memory-bandwidth slope, physical roofline and stall causes: unknown.</text>',
                  '<text x="30" y="491" font-size="13">Logical actor completion is qualified inside each ROI; this is not a physical utilization measurement.</text>', '</g></svg>'])
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source_path = ROOT / 'build/throughput-limits-source-v3/report.json'
    profile_path = ROOT / 'build/full-graph-VME-profile-v4/report.json'
    if sha(source_path) != SOURCE_SHA or sha(profile_path) != PROFILE_SHA:
        raise ValueError('Exact reviewed source capacity and execution proof required')
    source, proof = load(source_path), load(profile_path)
    inputs = {str(source_path): SOURCE_SHA, str(profile_path): PROFILE_SHA}
    for record in (source, proof):
        if record.get('pass') is not True:
            raise ValueError('Passing independent source and execution proofs required')
        verify_map(record['input_sha256'], inputs)
    verify_map(proof['artifact_sha256'], inputs, profile_path.parent)
    run_path = ROOT / 'build/full-graph-VME-buffered-full-v4/run.json'
    run = load(run_path)
    verify_map(run['input_sha256'], inputs); verify_map(run['output_sha256'], inputs)
    if (run.get('pass') is not True or type(run.get('exit_status')) is not int or run['exit_status'] != 0 or
            run.get('timed_out') is not False or run.get('owned_process_cleanup_complete') is not True or
            run.get('debug_commands_end') != 'unbounded silent run; no quit command'):
        raise ValueError('Actual normal guest completion and owned cleanup required')
    graph = load(ROOT / 'build/full-graph-VME-buffered-full-v4/graph.json')
    summary = load(profile_path.parent / 'summary.json')
    prefix_path = ROOT / 'build/full-graph-VME-buffered-full-v4/features.jsonl'
    prefixes = [json.loads(l) for l in prefix_path.read_text().splitlines()]
    inputs[str(prefix_path)] = sha(prefix_path)
    if graph.get('schema_version') != 1 or graph.get('hart_cycle_dividers') != [1, 1, 1] or graph.get('base_clock_hz') != 500000000:
        raise ValueError('Qualified actual source calendar required')
    capture = graph['counter_read_observations']
    if capture.get('complete') is not True:
        raise ValueError('Complete captured CSR observations required')
    # Re-execute independent per-word golden and actual instruction/CSR joins.
    from timing.profile_vme_full_graph_v4 import decode
    from iris_model.guest_regions import Instructions
    from iris_model.counter_regions import observations
    from iris_model.report import symbols
    nm = '/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-nm'
    symbol_table = symbols(ROOT / 'build/full-graph-VME-guest-buffered-v4/profile-vme.elf', nm)
    decoded, checked_words = decode((ROOT / 'build/full-graph-VME-buffered-full-v4/stderr').read_text())
    reads = observations(graph, Instructions(ROOT / 'build/full-graph-VME-guest-buffered-v4/profile-vme.elf', ROOT / 'board/evidence/bootrom.rv64.img'))
    regions = []
    if source['nominal_clock_conversion']['core_hz_by_hart'] != [graph['base_clock_hz']] * 3:
        raise ValueError('Source core and model global clock calendar mismatch')
    for window in summary['observed_regions']:
        hart, start, end = window['hart'], window['start_cycle'], window['end_cycle']
        endpoints = []
        for tick in (start, end):
            candidates = [p for p in prefixes if p['hart'] == hart and p['read_cycle'] == tick]
            if len(candidates) != 1:
                raise ValueError('Exactly one actual CSR prefix at each boundary required')
            p = candidates[0]
            if (p.get('feature_semantics') != 'architecturally_retired_instruction_features' or
                    p.get('memory_semantics') != 'accepted_timing_intents' or
                    p.get('endpoint') != 'get_csr_before_current_instruction_retirement'):
                raise ValueError('Exact retired-feature and accepted-intent scopes required')
            matches = [r for r in reads if all(r.get(k) == p.get(k) for k in ('hart', 'sequence', 'value', 'pc', 'raw', 'csr', 'destination', 'read_cycle'))]
            if len(matches) != 1 or p.get('result_discarded') is not False:
                raise ValueError('Actual ELF-checked CSR join required')
            endpoints.append(p)
        before, after = endpoints
        matches = [r for r in decoded if r['hart'] == hart and r['case_id'] + '::kernel' == window['region']]
        if len(matches) != 1 or matches[0]['start_cycle'] != before['value'] or matches[0]['end_cycle'] != after['value']:
            raise ValueError('Actual stored counter readback differs from graph')
        family = 'vme.fp8' if '.E4M3::' in window['region'] else 'vme.int8'
        selected = capacity(source['capacity_records'], hart, family)
        if selected and selected['value'] != 256:
            raise ValueError('Unexpected OPU source geometry')
        features, memory = delta(before['features'], after['features']), delta(before['memory'], after['memory'])
        retired_macs = sum(v.get('macs', 0) for v in features.values())
        expected = 4096 if hart < 2 else 0
        work = work_completion(graph['events'], hart, start, end)
        qualified = work['model_completion_window_qualified'] and work['completed_logical_MACs'] == retired_macs == expected
        if not qualified:
            raise ValueError('Modeled completion, retired semantics and independent algorithm must agree')
        # Check the actual kernel symbol contains every credited MAC origin PC.
        kernel = next(f for f in window['functions'] if f['function'] == ('matrix_kernel' if hart < 2 else 'producer_kernel'))
        bounds = [s for s in symbol_table if s[2] == kernel['function'] and s[0] == kernel['symbol_address']]
        if len(bounds) != 1:
            raise ValueError('Unique sized actual ELF kernel symbol required')
        for event in work['credited_operations']:
            if event['name'] != 'empirical.async.' + family or event['macs'] != 1024:
                raise ValueError('MAC actor kind or shape differs from actual four-operation kernel')
            if not bounds[0][0] <= integer(event['pc'], 'MAC origin PC') < bounds[0][1]:
                raise ValueError('MAC actor PC is outside actual ELF kernel')
        edges = clock_edges(start, end, graph['hart_cycle_dividers'][hart])
        ratio = conditional_fraction(retired_macs, edges, selected['value'] if selected else None, qualified)
        regions.append({
            'hart': hart, 'region': window['region'], 'family': family if selected else 'rvv.integer.control_no_VME',
            'global_window': {'start': start, 'end': end, 'ticks': end-start, 'convention': '[start,end)',
                              'guest_mcycle_delta': window['guest_mcycle_delta'], 'guest_counter_is_not_global_time': True,
                              'source_core_edge_opportunities': edges, 'divider': graph['hart_cycle_dividers'][hart], 'phase': 0,
                              'physical_clock_activity_observed': False},
            'actual_CSR_endpoints': [{k: p[k] for k in ('sequence','pc','raw','csr','destination','value','read_cycle')} for p in endpoints],
            'kernel_symbol': kernel['function'], 'kernel_symbol_address': kernel['symbol_address'],
            'kernel_symbol_end': bounds[0][1],
            'algorithm': {'TM': 32 if selected else None, 'TN': 32 if selected else None, 'TK': 1 if selected else None,
                          'MM_instructions': 4 if selected else 0, 'logical_MACs': retired_macs, 'formula': '4*32*32*1' if selected else 'no VME on hart2'},
            'completion': work, 'retired_feature_delta': features, 'accepted_intent_delta': memory,
            'source_capacity': selected, 'conditional_source_peak_fraction': ratio,
            'logical_MACs_per_potential_core_edge': retired_macs / edges if edges else None,
            'byte_coordinates': byte_coordinates(features, memory, retired_macs),
            'physical_OPU_utilization': None, 'physical_MAC_rate': None,
            'memory_bandwidth_bytes_per_second': None, 'memory_slope': None, 'physical_roofline': None, 'stall_breakdown': None,
        })
    if len(regions) != 6 or checked_words != 144:
        raise ValueError('Actual six-ROI corpus and all active output words required')
    inputs[str(Path(__file__).resolve())] = sha(__file__)
    payload = {
        'schema': 'iris.conditional_source_capacity_overlay.v1',
        'pass': not any(r['conditional_source_peak_fraction']['inconsistency'] for r in regions),
        'inconsistency': any(r['conditional_source_peak_fraction']['inconsistency'] for r in regions),
        'regions': regions, 'source_report_sha256': SOURCE_SHA, 'execution_proof_sha256': PROFILE_SHA,
        'ELF_sha256': run['ELF_sha256'], 'native_binary_sha256': run['native_binary_sha256'],
        'normal_HTIF_exit': True, 'full_graph_partial_at_exit': graph['partial'],
        'full_graph_pending_operations': graph['pending_operations'],
        'ROI_logical_MAC_completion_qualified': True, 'physical_MAC_completion_verified': False,
        'scope': 'logical completed model work / conditional source ceiling using potential source edges in actual captured CSR global windows',
        'intensity_scope': 'ROI-local retired requested data bytes, including scalar/control data; excludes operand setup outside ROI, VRF moves, instruction fetch; not physical cache or DRAM traffic',
        'source_conditions': 'The 256-MAC accepted-array-edge capacity is a conditional upper bound, not a guaranteed whole-instruction rate. FP8 hazards, masks, TM/TN/TK, VRF, setup and drains remain relevant.',
        'source_nominal_clock_conversion': source['nominal_clock_conversion'],
        'source_non_additivity': source['non_additivity'],
        'physical_memory_bandwidth': None, 'memory_slope': None, 'physical_roofline': None,
        'hardware_contacted': False, 'global_heldout_timings_consumed': False,
        'calibration_changed': False, 'source_image_association_verified': False, 'timing_2pct_certified': False,
        'input_sha256': inputs,
    }
    (args.output/'overlay.json').write_text(json.dumps(payload, indent=2)+'\n')
    (args.output/'overlay.svg').write_text(render_svg(regions))
    verify_map(inputs, {})
    receipt = {'schema': 'iris.conditional_capacity_overlay_receipt.v1', 'pass': payload['pass'],
               'regions': len(regions), 'logical_MACs': sum(r['algorithm']['logical_MACs'] for r in regions),
               'active_output_words_independently_checked': checked_words,
               'input_sha256': inputs, 'artifact_sha256': {n: sha(args.output/n) for n in ('overlay.json','overlay.svg')},
               'hardware_contacted': False, 'global_heldout_timings_consumed': False}
    (args.output/'report.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps({'pass': payload['pass'], 'regions': len(regions), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
