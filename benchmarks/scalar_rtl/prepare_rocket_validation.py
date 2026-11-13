#!/usr/bin/env python3
"""Freeze fresh Rocket/Shuttle component shapes before their RTL timing measurements."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from build import ROOT,sha
sys.path.insert(0,str(ROOT))
from iris_model.guest_regions import Instructions


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    parent=ROOT/'build/scalar-rtl-probe-v1/build.json';base=json.loads(parent.read_text())
    for path,digest in base['input_sha256'].items():
        if sha(path)!=digest:raise ValueError('parent source changed '+path)
    original_guest=ROOT/'benchmarks/scalar_rtl/guest.c';original_stream=ROOT/'benchmarks/scalar_rtl/streams.S'
    rows=[]
    for count in (4,5,6,15,16,17,33,65,127,255):
        case=out/('alu'+str(count));case.mkdir();guest=original_guest.read_text();stream=original_stream.read_text()
        for old,new in [('!=257','!='+str(count+1)),('!=292','!='+str(count+36))]:
            if guest.count(old)!=1:raise ValueError('unexpected checksum template')
            guest=guest.replace(old,new)
        replacements={'.rept 256':'.rept '+str(count),'.rept 32':'.rept '+str(count//8),'li a1,256':'li a1,'+str(count)}
        for old in replacements:
            if stream.count(old)!=1:raise ValueError('unexpected instruction template')
        stream=re.sub('|'.join(re.escape(old) for old in replacements),lambda match:replacements[match[0]],stream)
        for old,new in [('scalar_dep256','scalar_dep_body'),('scalar_ind256','scalar_ind_body')]:
            guest=guest.replace(old,new);stream=stream.replace(old,new)
        # Test odd packet boundaries as well as complete eight-chain groups.
        split=stream.index('scalar_ind_body:');first,second=stream[:split],stream[split:]
        marker='  .endr\n  TIME_END'
        if second.count(marker)!=1:raise ValueError('unexpected independent-body end')
        registers=['t0','t1','t2','t3','a2','a3','a4','a5']
        tail=''.join('  addi '+reg+','+reg+',1\n' for reg in registers[:count%8])
        stream=first+second.replace(marker,'  .endr\n'+tail+'  TIME_END')
        gc=case/'guest.c';ss=case/'streams.S';gc.write_text(guest);ss.write_text(stream);elf=case/'scalar.elf'
        argv=list(base['argv']);argv[argv.index(str(original_guest))]=str(gc);argv[argv.index(str(original_stream))]=str(ss);argv[-1]=str(elf)
        result=subprocess.run(argv,capture_output=True,text=True);(case/'build.log').write_text(result.stdout+result.stderr)
        if result.returncode:raise RuntimeError('validation probe build failed')
        nm=Path(argv[0]).with_name('riscv64-unknown-elf-nm')
        symbols=subprocess.check_output([nm,'-n',elf],text=True)
        (case/'symbols.txt').write_text(symbols)
        addresses={parts[-1]:int(parts[0],16) for line in symbols.splitlines() if len(parts:=line.split())==3}
        image=Instructions(elf);bodies=[]
        for label in ['scalar_dep_body','scalar_ind_body']:
            pc=addresses[label];counter_pcs=[]
            for _ in range(count+128):
                word=image.read(pc)
                if word==0x8067:break
                if word&127==0x73 and word>>20 in (0xB00,0xB02):counter_pcs.append(pc)
                pc+=4
            else:raise ValueError('missing straight-line body return')
            if len(counter_pcs)!=4:raise ValueError('wrong counter bracket shape')
            ops=[]
            for pc in range(counter_pcs[1]+4,counter_pcs[2],4):
                word=image.read(pc);rd=(word>>7)&31
                if word&0x707f!=0x13 or word>>20!=1 or (word>>15)&31!=rd or not rd:
                    raise ValueError('validation body is not ADDI chains')
                ops.append(rd)
            if len(ops)!=count or len(set(ops))!=(min(count,8) if label=='scalar_ind_body' else int(count>0)):
                raise ValueError('compiled validation body count/chain mismatch')
            bodies.append({'symbol':label,'counter_pcs':counter_pcs,'decoded_addi_operations':len(ops),'destination_registers':sorted(set(ops))})
        inputs={**base['input_sha256'],str(Path(__file__).resolve()):sha(Path(__file__)),str(parent):sha(parent),str(gc):sha(gc),str(ss):sha(ss)}
        inputs[str(nm)]=sha(nm)
        receipt={'schema':'iris.scalar_component_validation_build.v1','purpose':'frozen component validation, separate from final Merlin/Miles held-outs',
                 'alu_operations':count,'physical_harts':3,'bodies':['dependent','eight_independent_chains'],
                 'elf':str(elf),'elf_sha256':sha(elf),'argv':argv,'input_sha256':inputs,
                 'expected_checksums':[count+1,count+36],'counter_contract':'writable B00/B02 CSRRS x0; source-specific visible count',
                 'compiled_body_validation':bodies,
                 'reference_timing_observed_before_freeze':False,'timing_calibrated':False}
        (case/'inputs').mkdir()
        for path,digest in inputs.items():
            target=case/'inputs'/digest
            if not target.exists():shutil.copyfile(path,target)
        (case/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')
        rows.append({'case_id':'scalar.alu'+str(count),'operations':count,'build_receipt':str(case/'build.json'),
                     'build_receipt_sha256':sha(case/'build.json'),'elf_sha256':sha(elf)})
    plan={'schema':'iris.scalar_component_validation_plan.v1','cases':rows,'generator_sha256':sha(Path(__file__)),
          'reference_timings_observed':False,'model_predictions_frozen':False,'final_workload_holdout':False,
          'policy':'Freeze the new model predictions/binary and source before measuring these new RTL timings. Do not silently turn a failing case into fitting data.'}
    (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n');print(out/'plan.json')


if __name__=='__main__':main()
