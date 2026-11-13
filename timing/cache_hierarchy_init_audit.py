#!/usr/bin/env python3
"""Distinguish source simulation randomization from unproven FPGA memory INIT."""
import argparse
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=Path('/scratch/eygao/iris-cy/sims/firesim/deploy/results-build/2026-11-03--03-10-49-corigine_mimicturbo_gt_firesim_iris_tethered_bringup_nocflush/cl_corigine_mimicturbo_gt-firesim-FireSim-IrisFiresimNOCflushCombinedConfig-BaseCorigineMimicTurboGTConfig/design/FireSim-generated.sv')
PIN='c0f972d2a63be8170f7c84a38633fbede855f00d3022e81141fa0bb274397b64'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=ROOT/'build/cache-hierarchy-init-audit-v1');a=p.parse_args();out=a.output.resolve()
    if out.exists():raise ValueError('fresh initialization audit output required')
    if sha(ARCHIVE)!=PIN:raise ValueError('archived generated FireSim RTL changed')
    out.mkdir();lines=ARCHIVE.read_text().splitlines();blocks={}
    for name in ('Queue16_ShuttleMSHRReq','ShuttleDCache'):
        start=next(i for i,l in enumerate(lines)if l.startswith('module '+name+'('));end=next(i for i in range(start+1,len(lines))if lines[i].startswith('endmodule'))
        body='\n'.join(lines[start:end+1])+'\n';path=out/(name+'.sv');path.write_text(body);blocks[name]={'start_line':start+1,'end_line':end+1,'snapshot':path.name,'sha256':sha(path)}
    queue=(out/'Queue16_ShuttleMSHRReq.sv').read_text()
    assert 'reg [159:0] ram_flattened [0:15]'in queue
    assert 'ram_flattened[ram_flattened_MPORT_addr] <= ram_flattened_MPORT_data'in queue
    initial=queue.index('initial begin');guard=queue.rfind('`ifndef SYNTHESIS',0,initial)
    assert guard>=0 and 'RANDOMIZE_MEM_INIT'in queue[initial:]
    assert 'ram_flattened[initvar] = _RAND_0[159:0]'in queue[initial:]
    reset_section=queue[queue.index('if (reset)'):queue.index('// Register and memory initialization')]
    assert 'ram_flattened['not in reset_section
    # Generic GoldenGate SRAM source is secondary evidence only; it is not
    # assumed to have been selected for this particular compiled queue.
    generic=Path('/scratch/eygao/iris-cy/sims/firesim/sim/midas/src/main/scala/midas/models/sram/AsyncMemModel.scala')
    (out/'AsyncMemModel.scala').write_bytes(generic.read_bytes())
    report={'schema':'iris.cache_unreset_fpga_convention_audit.v1','status':'no_source_level_target_reset_clear_or_attested_fpga_INIT',
        'archived_generated_sv':{'path':str(ARCHIVE),'sha256':PIN},'module_excerpts':blocks,
        'queue_target_reset_clears_payload_memory':False,
        'queue_source_simulation_initialization':'RANDOMIZE_MEM_INIT in an initial block guarded by ifndef SYNTHESIS; one random160bit value assigned to all16 entries',
        'generic_GoldenGate_source':{'path':str(generic),'sha256':sha(generic),'snapshot':'AsyncMemModel.scala','selected_for_this_queue_verified':False,'fact':'host data Mem has no explicit target-reset clear'},
        'implemented_fpga_BRAM_LUTRAM_INIT_values':None,'implemented_init_convention_attested':False,'module_reachability_in_implemented_netlist_verified':False,
        'conclusion':'Do not substitute Verilator seed values or assumed FPGA zeros for an established implemented initialization convention. The standalone witness proves a legal unreset timing dependency; its realizations are not measurements of the loaded FireSim memory state.',
        'source_layout_difference':'Archived generated-SV Queue16 payload160bits; standalone firtool-lowered queue removes unused fields. Do not equate raw bit positions between these layouts.',
        'input_sha256':{str(Path(__file__)):sha(Path(__file__))},'hardware_contacted':False,'loaded_image_verified':False,'timing_certified':False}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
