"""Synthetic typed-write ownership controls; no guest/physical execution."""
from pathlib import Path
import argparse, importlib.util, json, subprocess
ROOT = Path(__file__).resolve().parents[2]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build-dir', type=Path, required=True)
    p.add_argument('--boost-include', type=Path)
    p.add_argument('--masked-packets', action='store_true')
    p.add_argument('--cold', action='store_true', help='exercise opt-in source-owned cold allocation')
    p.add_argument('--source-read', action='store_true', help='exercise source-owned ordinary LLC replacement')
    p.add_argument('--victim', action='store_true', help='exercise source-closed private victim snapshot')
    p.add_argument('--coherence-roles', action='store_true', help='exercise source-declared Get/Hint versus coherent private clients')
    p.add_argument('--dirty', action='store_true', help='exercise separate old-DRAM writeback ownership')
    args = p.parse_args(); build = args.build_dir.absolute()
    if build == ROOT or ROOT in build.parents:
        p.error('build directory must be outside checkout')
    build.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('fixture', ROOT/'timing/tests/run_native.py')
    fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
    model = fixture.fixture_model('0'*64)
    model['memory']['caches']['l2'] = dict(sets=16, ways=2, line_bytes=64, policy='write_back_write_allocate')
    model['memory']['paths'].update(cpu_data=['l1d','l2'], cpu_fetch=['l1i','l2'], device=['l2'])
    if args.coherence_roles:
        for name,kind in [('l1i','get_hint_noncoherent'),('l1d','probe_client')]:
            model['memory']['caches'][name]['coherence_role']=dict(schema='merlin.private_cache_coherence_role.v1',kind=kind,source_receipt_sha256='0'*64)
    model['parameters'].update({'memory.l2.hit_cycles':1, 'memory.l2.miss_cycles':1})
    model['resources'].append(dict(id=3,name='memory.l1d.probe',capacity=1,queue_capacity=2))
    model['memory']['caches']['l1d']['coherence_probe_service']=dict(schema='merlin.private_cache_probe_service.v1',resource='memory.l1d.probe',beat_bytes=16,lookup_cycles=2,dirty_enter_cycles=1,data_pipeline_cycles=2,metadata_cycles=1)
    model['memory']['device_write_request_pipeline'] = dict(
        schema='merlin.source_device_write_request_pipeline.v1', enabled=1, cache='l2',
        directory_stages=1, mshr_plan_stages=1, scalar_lookup_cycles=1, source_receipt_sha256='0'*64)
    model['memory']['device_write_request_pipeline']['single_private_probe']=dict(schema='merlin.selected_probe_sinkc_handoff.v1',line_bytes=64,beat_bytes=16,sinkc_queue_stages=1,mshr_response_register_stages=1,banked_store_banks=8,banked_store_write_bytes=8,source_receipt_sha256='0'*64)
    if args.cold:
        model['memory']['device_write_miss_pipeline']=dict(schema='merlin.selected_cold_write_miss.v1',enabled=1,cache='l2',line_bytes=64,outer_beat_bytes=8,demand_mshrs=10,source_receipt_sha256='0'*64)
        if args.dirty:
            model['memory']['device_write_miss_pipeline']['dirty_victim']=dict(schema='merlin.selected_sourcec_dirty_writeback.v1',sourcec_read_pipeline_stages=2,sourcec_queue_entries=12,line_beats=8,outer_beat_bytes=8,banked_store_priority='sinkc_sourcec_sinkd_sourcedw_sourcedr',source_receipt_sha256='0'*64)
    if args.victim:
        model['memory']['device_write_miss_pipeline']['private_victim']=dict(schema='merlin.selected_private_victim_probe.v1',private_cache='l1d',clients=1,line_bytes=64,inner_c_entries=2,sinkc_entries=1,postgrant_guard=8,cpu_readiness='accepted_completion_upper_bound',source_receipt_sha256='0'*64)
    if args.source_read:
        model['parameters']['memory.dram_per_byte_cycles']=0.0625 # synthetic <=8-beat byte-service floor
        # Exercise the formerly overlapping legacy I$ refill approximation:
        # V7 must own the actual lower lookup instead of subtracting a price
        # that this legacy route suppressed on I$miss/LLChit.
        model['memory']['fetch_refill_timeline']=dict(
            schema='merlin.provisional_fetch_refill.v1',
            assumptions='demand_only_immediate_replay_no_backpressure',
            beat_bytes=16,beat_interval_cycles=1,first_response_cycles=6,
            line_visible_after_last_cycles=1,lookup_response_cycles=2,
            request_accept_cycles=2)
        model['memory']['source_read_allocations']=dict(schema='merlin.selected_source_read_allocations.v1',enabled=1,cache='l2',directory_stages=1,mshr_plan_stages=1,source_d_stages=2,source_receipt_sha256='0'*64)
    if args.masked_packets: model.setdefault('target',{}).setdefault('scheduling',{})['source_masked_packet_readout']=1
    path = build/'model.json'; path.write_text(json.dumps(model))
    flags = ['g++','-std=c++20','-O1','-g0','-I'+str(ROOT/'timing'),'-I'+str(ROOT/'timing/core/include')]
    if args.boost_include: flags += ['-I'+str(args.boost_include)]
    binary = build/'write_transaction'
    subprocess.run([*flags,str(ROOT/'timing/tests/test_write_transaction.cpp'),
                    str(ROOT/'riscv/annotated_timing_memory.cc'),str(ROOT/'riscv/annotated_timing_model.cc'),
                    '-lcrypto','-o',str(binary)],check=True,timeout=90)
    subprocess.run([str(binary),str(path)],check=True,timeout=10)

if __name__ == '__main__': main()
