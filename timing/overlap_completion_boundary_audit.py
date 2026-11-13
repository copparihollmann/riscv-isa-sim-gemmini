#!/usr/bin/env python3
"""Static source control audit, qualified by the actual captured CSR opcodes."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);a=ap.parse_args();o=Path(a.output).resolve();o.mkdir(parents=True,exist_ok=False)
 sources={
  'uop':ROOT/'third_party/shuttle/src/main/scala/common/MicroOp.scala',
  'core':ROOT/'third_party/shuttle/src/main/scala/exu/Core.scala',
  'seq':ROOT/'third_party/saturn/src/main/scala/backend/OuterProductSequencer.scala',
  'backend':ROOT/'third_party/saturn/src/main/scala/backend/Backend.scala',
  'integration':ROOT/'third_party/saturn/src/main/scala/shuttle/Integration.scala',
  'associated_core':ROOT/'build/throughput-limits-source-v3/modules/ShuttleCore.sv'}
 text={k:p.read_text()for k,p in sources.items()};assert 'def system_insn = ctrl.csr === CSR.I'in text['uop'];assert '(uop.system_insn || ctrl.fence || uop.sfence || ctrl.fence_i || amo_fence)'in text['core'];assert 'io.busy := valid'in text['seq'];assert 'fp8_hist_valid = RegInit(0.U(fp8MaccLatency.W))'in text['seq'];assert 'clearVat(vos.io.iss.fire && vos.io.tail, vos.io.vat)'in text['backend'];assert "rrd_uops_0_bits_ctrl_csr == 3'h4"in text['associated_core'];assert 'io_vector_backend_busy | io_vector_trap_check_busy'in text['associated_core']
 prefix=ROOT/'build/overlap-completion-entry-queue-final-ON-v1/features.jsonl';rows=[json.loads(l)for l in prefix.read_text().splitlines()];assert len(rows)==672
 for row in rows:
  assert row['csr']==0xb00 and ((row['raw']>>12)&7)==2 and ((row['raw']>>15)&31)==0
 paths=[Path(__file__).resolve(),*sources.values(),prefix,ROOT/'build/throughput-limits-source-v3/report.json']
 report={'schema':'iris.opu_entry_boundary_source_audit.v1','pass':True,'source_scope':'Associated saved ShuttleCore control plus readable Saturn source; separate from FPGA image and complete CPU/unit coupling','ordinary_mcycle_ministret_CSR_read_is_system_insn':False,'mcycle_reads_qualified':672,'CSR_encoding':'CSRRS mcycle,rs1=x0; CSR.S not CSR.I; pipeline/scoreboard timing may still stall','source_FENCE_busy_gate':'backend_busy || trap_check_busy plus ordered memory/scalar scoreboard; not blanket physical completion','source_OPU_busy_excludes_FP8_tail':True,'VAT_release':'last sequencer microissue, not final FP8 write','native_FENCE_and_config_policy':'conservative wait for all entry-owned writes; explicitly NOT exact source FENCE issue timing','IRQ_policy':'active contexts refused, not silently drained as a source-exact claim','cycle_boundaries':'start→issue_end→fence_end→dependent readout+store+fence end; total minstret only','input_sha256':{str(p):sha(p)for p in paths},'hardware_contacted':False,'timing_reference_consumed':False,'source_image_association':False}
 (o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'sha256':sha(o/'report.json')}))
if __name__=='__main__':main()
