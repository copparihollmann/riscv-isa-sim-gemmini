"""Emit the current calibration readiness report without inventing timing values."""
import hashlib
import json
from pathlib import Path


def scalar_observation(path):
    """Read the separately frozen, explicitly unqualified same-ELF observation."""
    path=Path(path);base=path.parent.resolve();report=json.loads(path.read_text())
    if (report.get('schema')!='iris.scalar_rtl_observation.v1' or
        report.get('qualified_accuracy') is not False or report.get('held_out_validation') is not False or
        report.get('timing_calibrated') is not False or report.get('ethan_image_association_verified') is not False or
        report.get('strict_counter_check_passed') is not False):
        raise ValueError('unqualified scalar observation contract required')
    for name,digest in report['artifact_sha256'].items():
        artifact=(base/name).resolve()
        if base not in artifact.parents or hashlib.sha256(artifact.read_bytes()).hexdigest()!=digest:
            raise ValueError('changed scalar observation artifact '+name)
    runs={};raw={}
    for tag in ('reference','model'):
        run=json.loads((base/tag/'results.json').read_text());runs[tag]=run
        if run['exit_status']!=0 or run['timed_out'] is not False:raise ValueError('failed scalar process')
        words=[int(line,16) for line in (base/tag/'signature').read_text().splitlines()]
        if len(words)!=56 or words[:8]!=[0x495249535343414c,1,0,1,1,1,0,0]:raise ValueError('failed/incomplete scalar mailbox')
        rows=[]
        for hart in range(3):
            for kind in range(2):
                start,end,ibegin,iend,checksum,ops,pad0,pad1=words[8+hart*16+kind*8:16+hart*16+kind*8]
                if end<=start or iend<=ibegin or checksum!=(257 if kind==0 else 292) or ops!=256 or pad0 or pad1:
                    raise ValueError('invalid scalar observation')
                rows.append((end-start,iend-ibegin))
        raw[tag]=rows
        elf=run['argv'][-1]
        if run['input_sha256'][elf]!=report['same_elf_sha256']:raise ValueError('scalar ELF mismatch')
    if runs['reference']['status']!='failed' or runs['reference'].get('error')!='counter/checksum mismatch':
        raise ValueError('original strict reference failure must remain visible')
    if len(report['table'])!=6:raise ValueError('six scalar observations required')
    for i,row in enumerate(report['table']):
        rc,ri=raw['reference'][i];mc,mi=raw['model'][i]
        expected={'hart':i//2,'kernel':'dependent256' if i%2==0 else 'independent256',
                  'rtl_cycles':rc,'model_cycles':mc,'signed_error_percent':100*(mc-rc)/rc,
                  'within_2_percent':abs(mc-rc)*100<=2*rc,'rtl_instret_delta':ri,'model_instret_delta':mi,
                  'counter_contract_matches':ri==mi==257}
        if row!=expected:raise ValueError('scalar table disagrees with raw counter signature')
    return {'report':str(path),'report_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'source_fir_sha256':report['source_fir_sha256'],'same_elf_sha256':report['same_elf_sha256'],
            'table':report['table'],'strict_counter_check_passed':False,'admitted_for_calibration':False,
            'held_out_validation':False,'qualification':'Saved standalone RTL only; source/read-phase discrepancy and target-image association remain unresolved.'}


def frozen_scoped_report(path, schema):
    """Verify local evidence without promoting its timing/image qualification."""
    path=Path(path);base=path.parent.resolve();report=json.loads(path.read_text())
    if report.get('schema')!=schema or report.get('timing_calibrated') is not False or report.get('hardware_contacted') is not False:
        raise ValueError('unqualified local-reference evidence required')
    if report.get('matches_ethan_firesim_image',report.get('ethan_image_association_verified')) is not False:
        raise ValueError('local reference cannot assert deployed-image equivalence')
    if not report.get('artifact_sha256'):raise ValueError('frozen evidence closure missing')
    for name,digest in report['artifact_sha256'].items():
        artifact=(base/name).resolve()
        if base not in artifact.parents or hashlib.sha256(artifact.read_bytes()).hexdigest()!=digest:
            raise ValueError('changed scoped reference artifact '+name)
    return report,{'report':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                  'qualified_timing':False,'deployed_image_equivalence':False}


def scoped_references(root):
    result={}
    path=root/'build/csr-phase-proof-v2/report.json'
    if path.exists():
        report,identity=frozen_scoped_report(path,'iris.whole_cpu_counter_phase_proof.v1')
        proof=report['analysis']
        if proof['whole_cpu_source_counter_transitions_verified'] is not True or proof['model_counter_policy_corrected'] is not False:
            raise ValueError('source proof/model correction distinction changed')
        result['counter_phase']=dict(identity,sampled_edges=proof['sampled_counter_update_edges'],
            actual_counter_reads=proof['counter_read_instructions'],actual_shuttle_rf_writes=len(proof['shuttle_rf_writebacks']),
            source_behavior_verified=True,model_policy_corrected=False,regions=proof['regions'])
    path=root/'build/scalar-counter-alias-control-v2/report.json'
    if path.exists():
        report,identity=frozen_scoped_report(path,'iris.scalar_counter_alias_control.v1')
        if (report['analysis'].get('original_strict_collector_unchanged') is not True or
                report['analysis'].get('body_and_all_other_elf_bytes_identical') is not True):
            raise ValueError('counter alias control did not preserve its source/collector')
        result['counter_alias_control']=dict(identity,analysis=report['analysis'],model_policy_corrected=False)
    path=root/'build/opu-cell-rtl-proof-v2/results.json'
    if path.exists():
        report,identity=frozen_scoped_report(path,'iris.opu_cell_rtl_proof.v1')
        if report['checks']['status']!='passed_saved_opu_cell' or report['full_rtl_certified'] is not False:
            raise ValueError('selected OPU cell proof coverage changed')
        result['opu_cell_arithmetic']=dict(identity,checks=report['checks'],full_rtl_certified=False,
            scope='One explicitly initialized compute OPU cell: arithmetic/local state/pipeline only; no whole-array/decode/OS or image qualification.')
    path=root/'build/rtl-memory-frontier-v1/report.json'
    if path.exists():
        report,identity=frozen_scoped_report(path,'iris.saved_rtl_memory_frontier.v1')
        if report['cause_identified'] is not False or report['global_deadlock_proven'] is not False:
            raise ValueError('memory frontier diagnosis scope changed')
        result['memory_controls']=dict(identity,controls=report['controls'],
            count8_vs9_load_image_byte_changes=report['count8_vs9_load_image_byte_changes'],
            fp_arithmetic_present=report['guest_fp_arithmetic_instructions'],cause_identified=False,
            global_deadlock_proven=False,unknown_reset_behavior_proven_irrelevant=False)
    path=root/'build/rtl-memory-packets-v1/report.json'
    if path.exists():
        report,identity=frozen_scoped_report(path,'iris.saved_rtl_packet_frontier.v1')
        if report['cause_identified'] is not False or report['global_deadlock_proven'] is not False:
            raise ValueError('packet frontier diagnosis scope changed')
        result['memory_packets']=dict(identity,packets=report['packets'],cause_identified=False,
            global_deadlock_proven=False,sampling_alias_correction=report['sampling_alias_correction'])
    path=root/'build/rtl-selected-vector-references-v1/report.json'
    if path.exists():
        report,identity=frozen_scoped_report(path,'iris.selected_saved_rtl_vector_references.v1')
        if report['selected_probes_pass'] is not True or report['unfenced_memory_frontier_resolved'] is not False:
            raise ValueError('selected vector proof coverage changed')
        result['selected_vector_cases']=dict(identity,cases=report['cases'],
            scope=report['full_fpcomp_sequence_scope'],unfenced_frontier_resolved=False,
            host_poll_backoff_general_fix=False,full_rtl_certified=False)
    path=root/'build/rtl-memory-return-path-v1-final/report.json'
    if path.exists():
        report,identity=frozen_scoped_report(path,'iris.saved_rtl_memory_return_path.v1')
        if (report['bounded_allocation_starvation_mechanism_identified'] is not True or
                report['root_cause_complete'] is not False):
            raise ValueError('bounded return-path mechanism cannot claim complete root cause')
        result['memory_return_path']=dict(identity,bounded_allocation_mechanism_identified=True,
            root_cause_complete=False,interpretation=report['interpretation'],
            scope='Bounded source-matched local-router allocation behavior; no proof of infinite deadlock or FPGA fault.')
    path=root/'build/noc-router-component-v1-final/report.json'
    if path.exists():
        report,identity=frozen_scoped_report(path,'iris.native_local_router_return_branch.v1')
        if (report['pass'] is not True or report['continuous_internal_state'] is not True or
                report['observed_waiting_or_egress_availability_injected'] is not False or
                report['whole_router_certified'] is not False or report['whole_noc_certified'] is not False):
            raise ValueError('native local return branch cannot claim whole-network coverage')
        result['native_return_branch']=dict(identity,cases=report['cases'],
            continuous_native_edges=sum(case['cycles'] for case in report['cases'].values()),
            external_dependencies=report['external_dependencies'],
            whole_router_certified=False,whole_noc_certified=False,
            scope='Source-derived local return branch with continuous computed FIFO/arbitration/credit state; peer requests and downstream readiness remain external.')
    for name,directory,counts in (
        ('blinded_scalar_component_validation','scalar-component-validation-e060-v1',(0,1,2,3,7,8,31,32,64,512)),
        ('fresh_rocket_shuttle_component_validation','scalar-component-validation-rocket-fresh-v1',(4,5,6,15,16,17,33,65,127,255)),
    ):
        path=root/'build'/directory/'report.json'
        if not path.exists():continue
        from benchmarks.scalar_rtl.verify_components import audit
        report=json.loads(path.read_text())
        prediction=Path(report['prediction_path']).parent
        anchor=report['input_sha256'][str(prediction/'manifest.json')]
        verified=audit(path.parent,prediction,anchor)
        rows=report['comparisons']
        expected={(n,h,k) for n in counts for h in range(3) for k in range(2)}
        if (verified['rows']!=60 or len(rows)!=60 or
                {(r['operations'],r['hart'],r['kind']) for r in rows}!=expected):
            raise ValueError('blinded scalar component validation scope changed')
        result[name]=dict(report=str(path),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),comparisons=rows,
            per_hart=verified['per_hart'],prediction_manifest_sha256=anchor,
            all_regions_within_2_percent=verified['all_regions_within_2_percent'],
            qualified_timing=False,deployed_image_equivalence=False,final_workload_holdout=False,
            scope='Predictions frozen before measurements; distinct saved RTL, scalar component only, not full workload or FireSim certification.')
    return result


def main():
    root = Path(__file__).resolve().parent.parent
    hardware_path = root / "hardware/manifest.json"
    hardware = json.loads(hardware_path.read_text())
    access_path = root / "firesim/access-audit.json"
    access = json.loads(access_path.read_text())
    rtl_probe_path = root / "hardware/rtl-probe.json"
    observation_path=root/'build/scalar-rtl-observation-v1/report.json'
    observation=scalar_observation(observation_path) if observation_path.exists() else None
    scoped=scoped_references(root)
    if observation and 'counter_phase' in scoped:
        observation['qualification']='Saved standalone RTL only; source counter behavior is now proved, current model policy and deployed-image association remain unresolved.'
    safety_path=root/'build/fpga-safety-readonly-preflight.json'
    provisional = []
    scalar_bounds = []
    for trial in ("direct", "direct-2"):
        directory = root / "runs/fpga-smoke-access-enabled-001" / trial
        if not (directory / "run.json").exists():
            continue
        run = json.loads((directory / "run.json").read_text())
        stdout, stderr = directory / "stdout", directory / "stderr"
        if (run.get("exit_status") != 0 or
            hashlib.sha256(stdout.read_bytes()).hexdigest() != run["stdout_sha256"] or
            hashlib.sha256(stderr.read_bytes()).hexdigest() != run["stderr_sha256"] or
            "*** PASSED ***" not in stderr.read_text()):
            raise ValueError("invalid provisional hardware smoke receipt")
        rows = [json.loads(line.split(" ", 1)[1]) for line in stdout.read_text().splitlines()
                if line.startswith("IRIS_REGION ")]
        provisional.append({"run": str(directory.relative_to(root)), "region_count": len(rows),
                            "elf_sha256": run["elf_sha256"], "driver_sha256": run["driver_sha256"],
                            "loaded_image_attested": False, "admitted_for_calibration": False})
        if trial == "direct":
            for row in rows:
                if row["case_id"] == "scalar.dep.1024" and row["hart"] in (0, 1):
                    cycles = row["end_cycle"] - row["start_cycle"]
                    # Conservative two-instruction boundary allowance. The
                    # current adapter requires positive whole-hart-cycle events
                    # and one outstanding instruction, hence at most IPC1.
                    bound = max(0, row["instret_delta"] - 2)
                    scalar_bounds.append({"case_id": row["case_id"], "hart": row["hart"],
                        "reference_cycles": cycles, "reference_retired": row["instret_delta"],
                        "one_in_flight_minimum_cycles": bound,
                        "minimum_signed_error_percent": 100*(bound-cycles)/cycles,
                        "conclusion": "Current one-in-flight adapter cannot meet 2%; source-accurate superscalar issue is required.",
                        "reference_qualification": "Provisional loaded-image association; not a calibration admission."})
    components = {
        "scalar_pipelines": ["issue widths", "dependency/branch stalls", "frontend misses"],
        "saturn": ["SEW/LMUL throughput", "sequencer/chaining", "scalar-vector overlap"],
        "vme": ["move/compute latency and overlap", "register-file dependencies", "tile hazards"],
        "local_memory": ["TCM/scratchpad access latency", "bank conflicts"],
        "shared_memory": ["cache miss behavior", "L2/NoC contention", "serial-TL payload bandwidth and latency"],
        "zephyr_smp": ["interrupt/preemption cost", "lock/barrier interference", "VME context interactions"],
    }
    result = {
        "schema_version": 1, "status": "unqualified_reference_observations_and_model_gaps", "certified": False,
        "hardware_manifest_sha256": hashlib.sha256(hardware_path.read_bytes()).hexdigest(),
        "access_evidence_sha256": hashlib.sha256(access_path.read_bytes()).hexdigest(),
        "image_sha256": access["image"]["sha256"],
        "source_image_association": hardware["artifact_source_association"],
        "new_reference_measurements": sum(run["region_count"] for run in provisional),
        "qualified_reference_measurements": 0,
        "provisional_reference_runs": provisional,
        "scalar_integration_feasibility": scalar_bounds,
        "standalone_rtl_scalar_observation": observation,
        "scoped_standalone_references":scoped,
        "fpga_safety_evidence_sha256": hashlib.sha256(safety_path.read_bytes()).hexdigest() if safety_path.exists() else None,
        "accuracy_target_percent": 2,
        "measured_signed_errors": None,
        "timing_simulator_mips": None,
        "rtl_probe": json.loads(rtl_probe_path.read_text()) if rtl_probe_path.exists() else None,
        "components": {name: {"status": "unassessed", "signed_error_percent": None,
                               "needs_measurements_for": needs} for name, needs in components.items()},
        "blockers": ["Current real operator allocation and complete all-user/device inspection/setup access; latest report has44 inaccessible processes and no allocation",
                     "Complete source/elaboration association with the deployed image",
                     "Source-proved counter/Rocket/reset-knownness fixes exist in isolated candidates; reviewed combined integration and certification are still required",
                     "Traffic-sensitive saved-RTL blocked memory-response/replay frontier; source/harness/unknown-reset contributions unresolved",
                     "Rocket/frontend/cache/vector/VME overlap/NoC timing beyond explicit synthetic fixtures",
                     "Fitting identification, repeatability and independent held-out validation with source-bound reference timing"],
        "interpretation": "Historical smoke observations and the original identical-ELF standalone RTL scalar table remain unqualified for FireSim calibration. The old646 model's independent256 row was+2.94%; it is historical evidence, not the latest isolated candidate. Source CSR/whole-CPU/alias proofs explain counter behavior, and separately frozen counter-pipeline candidates implement it; primary5e6 is unchanged. New blinded component validation, when present above, is scoped to its exact candidate/ELFs and distinct saved RTL. Source-matched native return-branch queue/arbitration/credit behavior is now reproduced continuously; whole-router/network and deployed-image behavior remain unqualified. No full-workload held-out accuracy claim exists. Actual compiler/Zephyr functional/context gates pass on their recorded frozen epochs; integration and full hardware/timing qualification remain open.",
    }
    output = root / "build/feasibility.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(output)


if __name__ == "__main__": main()
