#!/usr/bin/env python3
"""Source-only quiet-protocol audit; no claim about the stalled physical run."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 o=R/'build/rvv-quiet-WFI-source-audit-v2';o.mkdir(exist_ok=False)
 paths=[Path(__file__),R/'third_party/rocket-chip/src/main/scala/rocket/CSR.scala',R/'third_party/shuttle/src/main/scala/exu/Core.scala',R/'benchmarks/rvv_identify_tk_v3/guest.c',R/'benchmarks/rvv_identify_tk_v3/runtime/start.S']+[R/'build/rtl-verilator/gen-collateral'/n for n in['CSRFile.sv','CSRFile_2.sv']]
 csr=paths[1].read_text();assert'val pending_interrupts = high_interrupts | (read_mip & reg_mie)'in csr and'when (pending_interrupts.orR || io.interrupts.debug || exception) { reg_wfi := false.B }'in csr
 for p in paths[-2:]:
  text=p.read_text();line=next(x for x in text.splitlines()if'reg_wfi <='in x and'_GEN_5[3]'in x);assert'reg_mstatus_mie'not in line
 report=dict(schema='iris.quiet_WFI_MSIP_source_audit.v1',status='source_equations_verified',hardware_contacted=False,actual_stall_cause_known=False,source_image_full_association_verified=False,facts=[{'source':'CSR.scala:660,670,676,1093-1094,1231','fact':'MSIP enters read_mip; locally enabled pending is independent of globalMIE. LocallyenabledMSIP clears WFI; globalMIE separately gates trapdelivery.'},{'source':'configured CSRFile.sv:238,701;CSRFile_2.sv:968','fact':'Actual associated specialization clears reg_wfi on mie.MSIE&mip.MSIP without globalMIE.'},{'source':'rvv_identify_tk_v3/runtime/start.S:45-49;guest.c wait_epoch/benchmark_main','fact':'CRT enablesmie.MSIE. Guestclears globalMIE and writesmie=MSIE; inactivepeer publishesparkedepoch, waitscompletion thenpendingMSIP, thenacknowledges. Activewaitsallparked, publishescompletion beforefencedMSIPwrites.'}],scope='Staticprotocol/sourceaudit; no actualCLINTdelivery/targetPC/vector-drain observation. MIE0alone is not a source-supported stallcause. Runtimecoherence, outstandingVU, source/imageassociation remainunresolved.',input_sha256={str(p):sha(p)for p in paths})
 (o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(sha(o/'report.json'))
if __name__=='__main__':main()
