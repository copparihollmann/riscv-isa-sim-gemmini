#!/usr/bin/env python3
"""Freeze the source basis of the narrow Rocket pipeline without fitting costs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=ROOT/'build/rocket-pipeline-source-audit');a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=True,parents=True)
    pin='fc745a8c377fdbf1d278eea81da9ac47b4b5fbc0';repo=ROOT/'third_party/rocket-chip'
    if subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()!=pin:raise ValueError('Rocket source pin changed')
    shared=json.loads((ROOT/'timing/shuttle_issue_sources.json').read_text());controls={r['name']:r for r in shared['rows']}
    names=('LUI','AUIPC','ADDI','SLTI','SLTIU','XORI','ORI','ANDI','SLLI','SRLI','SRAI','ADD','SUB','SLL','SLT','SLTU','XOR','SRL','SRA','OR','AND','ADDIW','SLLIW','SRLIW','SRAIW','ADDW','SUBW','SLLW','SRLW','SRAW')
    for name in names:
        row=controls[name]
        if row['class'] not in ('IDecode','I64Decode') or 'WXD' not in row['flags'] or set(row['flags'])-{'RXS1','RXS2','WXD'}:
            raise ValueError('admitted base operation has broader controls: '+name)
    decode=repo/'src/main/scala/rocket/IDecode.scala'
    if sha(decode)!=shared['sources']['scalar-decode']['sha256']:raise ValueError('shared scalar decoder is not the pinned Rocket decoder')
    source=repo/'src/main/scala/rocket/RocketCore.scala';text=source.read_text()
    required=['require(decodeWidth == 1','val id_csr = Mux','val bypass_sources = IndexedSeq(',
              'ex_reg_valid := !ctrl_killd','mem_reg_valid := !ctrl_killx','wb_reg_valid := !ctrl_killm',
              'val ex_cannot_bypass = ex_ctrl.csr =/= CSR.N','val mem_cannot_bypass = mem_ctrl.csr =/= CSR.N',
              'csr.io.retire := wb_valid','Mux(wb_ctrl.csr =/= CSR.N, csr.io.rw.rdata,',
              'when (addr === raddr) { rdata := data }']
    if any(fragment not in text for fragment in required):raise ValueError('Rocket pipeline source structure changed')
    evidence={}
    for label,path,lines in [('rocket-core',source,[[320,324],[350,355],[463,480],[555,565],[661,679],[735,749],[846,855],[880,884],[1040,1104],[1372,1393]]),
                             ('scalar-decode',decode,[[19,69],[72,142]]),
                             ('rocket-ibuf',repo/'src/main/scala/rocket/IBuf.scala',[[78,91]]),
                             ('iris-config',ROOT/'third_party/chipyard/generators/chipyard/src/main/scala/config/IrisConfigs.scala',[[285,300]])]:
        target=out/(label+'.scala');shutil.copy2(path,target)
        evidence[str(path.relative_to(ROOT))]=dict(sha256=sha(path),snapshot=target.name,lines=lines,
                    repository_sha=pin if path.is_relative_to(repo) else 'b4542facf6cc9457f6e358e8f80a8b3a0ff5df19')
    report=dict(schema='iris.rocket.pipeline_source_audit.v1',status='passed_rocket_source_subset_audit',source_evidence=evidence,
                source_sha256={str(Path(__file__).relative_to(ROOT)):sha(__file__),'timing/shuttle_issue_sources.json':sha(ROOT/'timing/shuttle_issue_sources.json'),
                               'timing/shuttle_decode_rows.inc':sha(ROOT/'timing/shuttle_decode_rows.inc'),'build/pipeline-rvc-source-check/results.json':sha(ROOT/'build/pipeline-rvc-source-check/results.json')},
                admitted_base_instructions=[controls[n] for n in names],issue_width=1,retire_width=1,active_stages=['EX','MEM','WB'],
                ALU_result='EX',counter_result='WB',counter_zero_operand_rewrite='CSR.R',CSR_RAW_WAW_interlocks=['EX','MEM'],
                no_global_counter_drain=True,RF_write_through_to_ID=True,frontend='explicit sequential fixture; no cache/prediction qualification',
                unknown_parameters=dict(frontend_fetch_latency=None,cache_miss_penalties=None,branch_recovery=None,vector_overlap=None,memory_route_costs=None),
                calibrated=False,rtl_certified=False,held_out_2pct=False,ethan_image_association_verified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],base_operations=len(names))))


if __name__=='__main__':main()
