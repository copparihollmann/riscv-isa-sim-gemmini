#!/usr/bin/env python3
"""Freeze and verify the two completed selected local RTL reference probes."""
import argparse,hashlib,json,re,shutil,struct,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
EXPECTED={'hpm':(1,119),'rdtime':(2,5)}
FIELDS=['stage','actual','expected','cause','pc','tval','checks','done']

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_image(path):
    data=Path(path).read_bytes()
    if data[:6]!=b'\x7fELF\x02\x01':raise RuntimeError('Expected RV64 little-endian ELF')
    header=struct.unpack_from('<16sHHIQQQIHHHHHH',data)
    image={'entry':header[4],'segments':[]}
    for index in range(header[10]):
        typ,flags,off,va,pa,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',data,header[5]+index*header[9])
        if typ==1:image['segments'].append({'vaddr':va,'paddr':pa,'filesz':filesz,'memsz':memsz,'flags':flags,'align':align,'bytes':data[off:off+filesz].hex()})
    return image

def decode(path,name):
    lines=path.read_text().splitlines()
    if len(lines)!=28 or any(not re.fullmatch('[0-9a-f]{16}',x) for x in lines):raise RuntimeError('Invalid coherent RTL mailbox signature')
    words=[int(x,16) for x in lines];kind,count=EXPECTED[name]
    if words[:4]!=[0x4952495350524f42,1,kind,0]:raise RuntimeError('Wrong or failed RTL mailbox')
    rows=[dict(zip(FIELDS,words[4+8*h:12+8*h]),hart=h) for h in range(3)]
    for row in rows:
        if row['done']!=1 or row['checks']!=count or row['actual']!=row['expected']:raise RuntimeError('Incomplete/mismatching RTL hart result')
        if name=='rdtime' and (row['cause'],row['tval'])!=(2,0xc01022f3):raise RuntimeError('rdtime trap evidence differs')
    return rows

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=ROOT/'build/rtl-reference-hpm-rdtime-final');p.add_argument('--verify',action='store_true');a=p.parse_args();out=a.output.resolve()
    if a.verify:
        j=json.loads((out/'reference.json').read_text())
        for name,digest in j['artifact_sha256'].items():
            if sha(out/name)!=digest:raise RuntimeError('Archived RTL reference changed: '+name)
        for name,row in j['probes'].items():
            if decode(out/row['signature'],name)!=row['harts']:raise RuntimeError('RTL signature decoder disagrees')
        print(json.dumps({'pass':True,'selected_probes':list(j['probes']),'full_rtl_certified':False}));return
    if out.exists():raise RuntimeError('Refuse to overwrite a frozen reference capsule')
    out.mkdir(parents=True)
    origins={}
    def save(path):
        path=Path(path).resolve()
        try:rel=path.relative_to(ROOT)
        except ValueError:rel=Path('external')/path.relative_to('/')
        dst=out/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dst);origins[str(rel)]={'path':str(path),'sha256':sha(path)};return str(rel)
    local=ROOT/'build/rtl-loader-diag';build=json.loads((local/'loader-build.json').read_text());base=json.loads((ROOT/'build/rtl-verilator/manifest.json').read_text())
    if sha(build['binary'])!=build['binary_sha256']:raise RuntimeError('RTL host adapter changed')
    paths=[Path(x) for x in build['input_sha256']]+[Path(build['binary']),local/'loader-build.json',local/'fast-probes-build.json',Path(base['source_fir']),Path(base['source_annotations']),ROOT/'hardware/manifest.json',ROOT/'hardware/memory-paths.json']
    for path,digest in build['input_sha256'].items():
        if sha(path)!=digest:raise RuntimeError('RTL build input changed: '+path)
    paths += [x for x in (ROOT/'board/rtl-loader').rglob('*') if x.is_file() and '__pycache__' not in str(x)]
    paths += [Path(x) for x in base['sim_source_sha256']]
    for path,digest in base['sim_source_sha256'].items():
        if sha(path)!=digest:raise RuntimeError('Generated RTL changed: '+path)
    compiler=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc');paths.append(compiler)
    compile_rows=json.loads((local/'fast-probes-build.json').read_text());rebuilds=[]
    for row in compile_rows:
        if row['name'] not in EXPECTED:continue
        paths += [Path(x) for x in row['argv'] if Path(x).is_file()]
        args=list(row['argv']);args[-1]=str(out/('rebuilt-'+row['name']+'.elf'))
        result=subprocess.run(args,capture_output=True,text=True)
        nm=str(compiler.with_name('riscv64-unknown-elf-nm'))
        old_symbols=subprocess.check_output([nm,'-g',row['elf']]);new_symbols=subprocess.check_output([nm,'-g',args[-1]])
        if result.returncode or load_image(args[-1])!=load_image(row['elf']) or old_symbols!=new_symbols:raise RuntimeError('Rebuilt selected RTL code/memory image or global symbols differ')
        rebuilds.append({'name':row['name'],'argv':args,'exit_status':result.returncode,'elf_sha256':sha(args[-1]),'matches_executed_full_elf':sha(args[-1])==row['elf_sha256'],'matches_executed_load_segments_and_entry':True,'matches_executed_global_symbols':True,'global_nm_sha256':hashlib.sha256(old_symbols).hexdigest(),'nonexecution_rebuild_difference':'GCC temporary object FILE symbol name in ELF .strtab differs; original executed ELF and its full SHA are retained'})
    probe_dir=ROOT/'build/definedness-dev/rtl-probes'
    paths += [probe_dir/'probe_runtime.h',probe_dir/'hpm_switch.h',ROOT/'benchmarks/runtime.h']
    for path in sorted(set(paths)):save(path)
    probes={}
    for name in EXPECTED:
        prefix=local/(name+'-fast-v2');r=json.loads(prefix.with_suffix('.json').read_text());elf=Path(r['argv'][-1])
        if r['exit_status'] or r['timed_out'] or r['binary_sha256']!=build['binary_sha256'] or sha(elf)!=r['elf_sha256']:raise RuntimeError('Unsuccessful or changed RTL run')
        files={ext:save(prefix.with_suffix('.'+ext)) for ext in ['json','signature','stdout','stderr']};files['elf']=save(elf)
        files.update(harts=decode(prefix.with_suffix('.signature'),name),host_seconds=r['host_seconds'],pass_=True)
        probes[name]=files
    j={'schema':'iris.selected_rtl_reference.v1','selected_probe_pass':True,'probes':probes,'simulator_binary_sha256':build['binary_sha256'],'base_simulator_binary_sha256':base['binary_sha256'],'saved_design':base['saved_design'],'source_fir_sha256':base['source_fir_sha256'],'memory_lowering':base['memory_lowering'],'loading':'source-supported native RAM preload during FESVR load_program only; actual TSI reset/IPI and coherent final signature reads','crt':'versioned start-loader-bss.S relies on identified FESVR PT_LOAD zero fill; boot timing/cache state differs from original ELF','fesvr_source_commit':'9c190a07c6838f6392bafa4ad83acea462c7f759','fesvr_library_source_build_association_verified':False,'hardware_writes':False,'full_rtl_certified':False,'reset_definedness_certified':False,'timing_calibrated':False,'matches_ethan_firesim_image':False,'calibration_usable_for_firesim':False,'origins':origins,'artifact_sha256':{str(x.relative_to(out)):sha(x) for x in sorted(out.rglob('*')) if x.is_file()}}
    j['selected_probe_rebuilds']=rebuilds
    (out/'reference.json').write_text(json.dumps(j,indent=2)+'\n');print(out/'reference.json')

if __name__=='__main__':main()
