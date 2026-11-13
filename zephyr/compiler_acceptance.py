#!/usr/bin/env python3
"""Verify real-MLIR Zephyr gates against full goldens and archived native bytes."""
import argparse,hashlib,importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def make_record():
    snapshot=ROOT/'build/zephyr-primary-0c0fd778';manifest=json.loads((snapshot/'manifest.json').read_text())
    historical_path=ROOT/'zephyr/historical-compiler-sources.json';historical=json.loads(historical_path.read_text())['artifacts']
    for item in historical.values():
        if sha(ROOT/item['path'])!=item['sha256']:raise ValueError('Historical compiler source changed')
    if manifest.get('state')!='final_native_provenance_frozen' or manifest.get('closure_unavailable'):raise ValueError('Await complete final native provenance freeze')
    for item in manifest['artifacts']:
        if sha(item['snapshot_path'])!=item['sha256']:raise ValueError('Frozen native bytes changed')
    model_sha=manifest['artifacts'][0]['sha256'];plugin_sha=manifest['artifacts'][1]['sha256'];provenance=manifest['provenance_snapshot']
    if sha(provenance['path'])!=provenance['sha256'] or json.loads(Path(provenance['path']).read_text())['binary_sha256']!=model_sha:raise ValueError('Wrong native provenance identity')
    for name,digest in manifest['source_snapshot_sha256'].items():
        if sha(snapshot/name)!=digest:raise ValueError('Frozen native source changed')
    for item in manifest['closure_snapshot'].values():
        if sha(snapshot/item['path'])!=item['sha256']:raise ValueError('Frozen native closure changed')
    spec=importlib.util.spec_from_file_location('iris_zephyr_pipeline',ROOT/'zephyr/compiler_pipeline.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    gates=[]
    for op in ('gemm','conv2d'):
      for workers in (1,2):
        directory=ROOT/f'build/zephyr-mlir-final/{op}-h{workers}';path=directory/'results.json';data=json.loads(path.read_text())
        if not data['pass'] or not data['real_merlin_mlir_executed'] or data['physical_harts']!=3 or data['cpu_producer_hart']!=2 or data['workers']!=workers or data['op']!=op or data['binary_sha256']!=model_sha or data['uart_sha256']!=plugin_sha:raise ValueError('Wrong compiler gate identity')
        for p,digest in data['source_sha256'].items():
            source=Path(p)
            if sha(source)!=digest:
                source=directory/'shipped-build/input-snapshot'/source.relative_to(ROOT)
                if not source.is_file() or sha(source)!=digest:
                    item=historical.get(p)
                    if not item or item['sha256']!=digest:raise ValueError('Missing historical compiler source: '+p)
        expected=[module.golden(op,j,64,64,64 if op=='gemm' else 72) for j in range(3)]
        for run in data['runs']:
            kind=run['kind'];folder=directory/(kind+'-run');build=directory/(kind+'-build')
            if not run['pass'] or run['exit_status'] or sha(folder/'stdout')!=run['stdout_sha256'] or sha(folder/'stderr')!=run['stderr_sha256'] or sha(build/'zephyr/zephyr.elf')!=run['elf_sha256'] or sha(build/'build.json')!=run['build_receipt_sha256'] or sha(folder/'disassembly')!=run['disassembly_sha256']:raise ValueError('Changed executable/results')
            proof=json.loads((build/'build.json').read_text())
            for name,digest in proof['input_sha256'].items():
                if sha(build/'input-snapshot'/name)!=digest:raise ValueError('Changed compiled source snapshot')
            values=[json.loads(line.split(' ',1)[1]) for line in (folder/'stdout').read_text().splitlines() if line.startswith('IRIS_COMPILER_RESULT ')]
            if values!=expected or run['producer']['vector_checksum']!=module.producer_golden() or not any(run['producer']['overlap_masks'][:2]):raise ValueError('Full numerical/producer validation failed')
            hits=run['kernel_instruction_audit']
            if (kind=='shipped' and not all(hits.values())) or (kind=='twin' and any(hits.values())):raise ValueError('Wrong compiled kernel instructions')
        gates.append({'op':op,'workers':workers,'path':str(path.relative_to(ROOT)),'sha256':sha(path),'programs':2,'jobs_per_program':3,'full_int32_and_w8a8_elements_per_program':12288})
    return {'schema':'iris.zephyr.compiler_acceptance.v1','status':'passed_real_mlir_zephyr_pipeline','generator_sha256':sha(Path(__file__)),'historical_source_fallback_sha256':sha(historical_path),'snapshot_manifest':str((snapshot/'manifest.json').relative_to(ROOT)),'snapshot_manifest_sha256':sha(snapshot/'manifest.json'),'native_binary_sha256':model_sha,'gates':gates,'programs':8,'all_int32_elements_checked':98304,'all_w8a8_elements_checked':98304,'physical_harts':3,'compute_harts':[0,1],'producer_hart':2,'real_merlin_mlir':True,'convolution_frontend':'producer-side im2col; compiled contraction endpoint','target_owned_vme_setup':True,'whole_model_worker_pool_qualified':False,'rtl_certified':False,'fpga_certified':False,'timing_certified':False}
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--verify',action='store_true');a=p.parse_args();data=make_record();path=ROOT/'zephyr/compiler-acceptance.json'
    if a.verify:
        if json.loads(path.read_text())!=data:raise ValueError('Compiler acceptance is stale')
    else:path.write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps({'status':data['status'],'programs':data['programs'],'all_int32_elements_checked':data['all_int32_elements_checked']}))
if __name__=='__main__':main()
