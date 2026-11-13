#!/usr/bin/env python3
"""Associated-source policy audit plus an actual physical-port Rocket witness."""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = 'c0f972d2a63be8170f7c84a38633fbede855f00d3022e81141fa0bb274397b64'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compact(text):
    return re.sub(r'\s+', ' ', re.sub(r'//[^\n]*', '', text))


GUARDS = {
    'DCache': [
        'wire [1:0] s1_victim_way = lfsr[1:0];',
        "wire [3:0] s2_victim_way = 4'h1 << s2_victim_way_r;",
        'wire [3:0] s2_victim_or_hit_way = s2_hit_valid ? s2_hit_way : s2_victim_way;',
        'wire _T_93 = nodeOut_d_ready & auto_out_d_valid;',
        'wire _GEN_261 = grantIsCached & d_last;',
        'assign lfsr_prng_io_increment = _T_93 & _GEN_261;',
    ],
    'Directory': [
        'wire [9:0] victimLFSR = _victimLFSR_T[9:0];',
        "wire [3:0] victimLTE = {10'h300 <= victimLFSR,10'h200 <= victimLFSR,10'h100 <= victimLFSR,1'h1};",
        'assign victimLFSR_prng_io_increment = io_read_valid;',
    ],
    'MSHR': [
        "wire _req_needT_T_8 = request_opcode == 3'h6 | request_opcode == 3'h7;",
        "wire [2:0] _final_meta_writeback_clients_T_13 = _req_needT_T_8 ? req_clientBit : 3'h0;",
    ],
}


def guard(name, text):
    body = compact(text)
    for literal in GUARDS.get(name, []):
        if literal not in body:
            raise ValueError('Changed associated expression: ' + name + ':' + literal)
    if name in ('ICache', 'ShuttleICache'):
        ports = re.findall(r'^\s*(?:input|output)\s+(?:\[[^\]]+\]\s*)?(auto_master_out_\w+)', text, re.M)
        if not ports or any('_b_' in p or '_c_' in p or '_e_' in p for p in ports):
            raise ValueError('Changed noncoherent Icache physical channel boundary')


def main(a):
    old_audit = ROOT / 'build/all3-Dcache-replacement-source-audit-v2/report.json'
    associated = json.loads(old_audit.read_text())
    sv = Path(next(p for p in associated['input_sha256'] if p.endswith('FireSim-generated.sv')))
    if sha(sv) != EXPECTED:
        raise ValueError('Associated whole generated RTL changed')
    mods = {m[1]: m[0] + '\n' for m in re.finditer(r'^module\s+(\w+)[\s\S]*?^endmodule', sv.read_text(), re.M)}
    names = tuple(GUARDS) + ('ICache', 'ShuttleICache', 'MaxPeriodFibonacciLFSR')
    for name in names:
        guard(name, mods[name])
    cpp = (ROOT / 'timing/empirical_cache_v9.cpp').read_text()
    install = cpp.split('void CacheHistoryV9::install_l2(', 1)[1].split('\n}', 1)[0]
    if 'for(auto&cache:l1_)' not in install or 'l1i_' in install:
        raise ValueError('Changed Icache inclusion boundary')
    icache_scala = [Path('/scratch/eygao/iris-cy/generators/rocket-chip/src/main/scala/rocket/ICache.scala'),
                    Path('/scratch/eygao/iris-cy/generators/shuttle/src/main/scala/ifu/ICache.scala')]
    for p in icache_scala:
        body = p.read_text()
        if 'tl_out.a.bits := edge_out.Get(' not in body:
            raise ValueError('Changed source Icache request kind')
    mutations = []
    for name, before, after in [
        ('DCache', 's1_victim_way = lfsr[1:0]', 's1_victim_way = invalid_way'),
        ('DCache', 'lfsr_prng_io_increment = _T_93 & _GEN_261', 'lfsr_prng_io_increment = cpu_miss'),
        ('Directory', 'victimLFSR_prng_io_increment = io_read_valid', 'victimLFSR_prng_io_increment = directory_miss'),
        ('MSHR', "_req_needT_T_8 ? req_clientBit : 3'h0", 'isGet ? req_clientBit : 0'),
    ]:
        if before not in mods[name]:
            raise ValueError('Mutation precondition missing')
        try:
            guard(name, mods[name].replace(before, after, 1))
        except ValueError:
            mutations.append({'module': name, 'changed_source': before, 'rejected': True})
        else:
            raise ValueError('Changed source mutation admitted')
    for name in ('ICache', 'ShuttleICache'):
        try:
            guard(name, mods[name].replace('endmodule', 'input auto_master_out_b_valid;\nendmodule'))
        except ValueError:
            mutations.append({'module': name, 'changed_source': 'added Probe input', 'rejected': True})
        else:
            raise ValueError('Coherent Icache mutation admitted')
    witness = a.witness.resolve()
    raw = [json.loads(x) for x in (witness / 'tool-combined-output.txt').read_text().splitlines()]
    if len(raw) != 3 or [x['seed'] for x in raw[:2]] != [1, 17] or not all(
            r['third_line_source_reacquires'] == r['third_line_V9_LRU_hits'] == 1 and
            r['source_responses'] == r['physical_A_requests'] == 5 for r in raw[:2]) or raw[2]['status'] != 'passed':
        raise ValueError('Changed actual physical-port witness')
    # Conditional expression-only selector trace; actual cache behavior above is separate.
    state, rocket_victims, l2_victims = 1, [], []
    for _ in range(4):
        rocket_victims.append(state & 3)
        state = ((state << 1) & 65535) | (((state >> 10) ^ (state >> 12) ^ (state >> 13) ^ (state >> 15)) & 1)
        l2_victims.append((state >> 8) & 3)
    if rocket_victims != [1, 2, 0, 0] or l2_victims != [0, 0, 0, 0]:
        raise ValueError('Source reset/selector trace changed')
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'associated-source').mkdir()
    for name in names:
        (out / 'associated-source' / (name + '.sv')).write_text(mods[name])
    inputs = [Path(__file__).resolve(), sv, old_audit, ROOT / 'timing/empirical_cache_v9.cpp',
              ROOT / 'timing/empirical_cache_v9.hpp',
              ROOT / 'hardware/cache_policy_followup_v1/rocket_victim_source_check.cpp',
              ROOT / 'timing/shuttle_memory_system_check.cpp'] + icache_scala
    inputs += [witness / x for x in ('argv.json', 'check', 'compile.stdout', 'compile.stderr', 'tool-combined-output.txt')]
    # Bind every linked frozen archive and the complete actual compile recipe.
    argv = json.loads((witness / 'argv.json').read_text())
    inputs += [Path(x) for x in argv if x.endswith('.a')]
    report = {
        'schema': 'iris.associated_cache_policy_followup.v1', 'pass': True,
        'associated_whole_RTL_sha256': EXPECTED, 'actual_physical_port_witness': raw,
        'concrete_mismatch': 'Rocket4way DCache reset victim sequence1,2,0,0 with '
            'finalcachedGrant advance replaces third line despite unusedway3; '
            'currentV9 RocketLRU retains all4. Actual5th load issues sourceAcquire versus V9L1hit.',
        'source_Rocket_advance': 'accepted final cachedGrant D beat, including permission-only cachedGrant; '
            'victim is captured in S1 before that response. No invalid-way preference.',
        'source_L2_replacement': 'Independent16bitLFSR/bank, victimstate[9:8], everyDirectory.io_read_valid '
            'includinghits; no invalid preference. CurrentV9 L2 LRU differs. Architecturalintent '
            'count does not establish exact Directory read sequence.',
        'instruction_inclusion_finding': 'Suspected V9L2eviction->privateIcache invalidation is FALSE. '
            'install_l2 invalidates only l1_D; publicAPI test preserves Icopy after verifiedL2eviction. '
            'AssociatedICache modules have onlyA/D channels; MSHRaddsclientbits onlyAcquire6/7, notGet4.',
        'conditional_only_selector_examples': {'Rocket_four_fills': rocket_victims,
                                               'L2_four_isolated_reads': l2_victims},
        'source_mutation_refusals': mutations,
        'limits': ['SourceSDK physical-port witness with explicitideal functionalpattern backing and '
                   'explicitFASEDLP30/30/16/16; not hardwaretiming/calibration.',
                   'No actual workload/history/error attribution proved.',
                   'No native/helper/parameters/policies/currentselection changed.',
                   'No thirdmode added to frozen2mode campaign.',
                   'Associatedgeneratedbuild only; fullsource/loadedimage attestationfalse.',
                   'No hardware or reserved/global timing labels accessed.'],
        'input_sha256': {str(p): sha(p) for p in inputs},
        'own_source_sha256': {str(p.relative_to(out)): sha(p) for p in (out / 'associated-source').glob('*')},
    }
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'pass': True, 'source_checks': raw[2]['source_and_model_checks'],
                      'source_mutants_refused': len(mutations), 'report_sha256': sha(out / 'report.json')}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--witness', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    main(p.parse_args())
