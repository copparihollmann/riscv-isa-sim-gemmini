"""Independently check the archived coherent signatures of selected CSR RTL probes."""
import hashlib,json,re,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def decode_signature(raw,name):
    lines=raw.splitlines()
    if len(lines)!=28 or any(not re.fullmatch('[0-9a-f]{16}',line) for line in lines):
        raise ValueError('Invalid selected RTL signature encoding')
    words=[int(line,16) for line in lines]
    kind,count=(1,119) if name=='hpm' else (2,5)
    if words[:4]!=[0x4952495350524f42,1,kind,0]:raise ValueError('Selected RTL mailbox failed or has wrong identity')
    rows=[]
    for hart in range(3):
        stage,actual,expected,cause,pc,tval,checks,done=words[4+8*hart:12+8*hart]
        if (checks,done)!=(count,1) or actual!=expected:raise ValueError('Selected RTL hart incomplete or failed')
        if name=='hpm' and (stage,actual,expected,cause,pc,tval)!=(7,0,0,0,0,0):
            raise ValueError('HPM completion state inconsistent')
        if name=='rdtime' and (stage,actual,expected,cause,tval)!=(5,1,1,2,0xc01022f3):
            raise ValueError('CSR time illegal-instruction proof inconsistent')
        rows.append({'hart':hart,'checks':checks,'done':done,'cause':cause,'pc':pc,'tval':tval})
    return rows

def elf_word(path,pc):
    raw=Path(path).read_bytes()
    if raw[:6]!=b'\x7fELF\x02\x01':raise ValueError('Selected probe must be ELF64 little endian')
    header=struct.unpack_from('<16sHHIQQQIHHHHHH',raw)
    for i in range(header[10]):
        kind,flags,offset,vaddr,paddr,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',raw,header[5]+i*header[9])
        if kind==1 and vaddr<=pc and pc+4<=vaddr+filesz:return int.from_bytes(raw[offset+pc-vaddr:offset+pc-vaddr+4],'little')
    raise ValueError('RTL trap PC outside probe load image')

def selected_csr_evidence(report=None):
    report=Path(report).resolve() if report is not None else ROOT/'build/rtl-reference-hpm-rdtime-final/reference.json'
    if not report.is_file():return {'tested':False,'reason':'Selected CSR RTL capsule not collected'},{}
    receipt=json.loads(report.read_text());evidence={str(report):sha(report)};capsule=report.parent
    if receipt.get('schema')!='iris.selected_rtl_reference.v1' or receipt.get('selected_probe_pass') is not True:
        raise ValueError('Selected CSR RTL capsule status invalid')
    for flag in ['full_rtl_certified','reset_definedness_certified','timing_calibrated','matches_ethan_firesim_image','calibration_usable_for_firesim']:
        if receipt.get(flag) is not False:raise ValueError('Selected CSR proof overstates certification')
    if set(receipt.get('probes',{}))!={'hpm','rdtime'}:raise ValueError('Selected CSR probe coverage missing')
    artifacts=receipt.get('artifact_sha256',{})
    if not artifacts or not receipt.get('origins'):raise ValueError('Selected CSR capsule has no source closure')
    for name,digest in artifacts.items():
        path=(capsule/name).resolve()
        if not path.is_relative_to(capsule) or not path.is_file() or sha(path)!=digest:
            raise ValueError('Selected CSR archived artifact digest mismatch')
        evidence[str(path)]=digest
    for name,row in receipt['origins'].items():
        if artifacts.get(name)!=row['sha256']:raise ValueError('Selected CSR origin/archive mismatch')
    decoded={}
    for name,probe in receipt['probes'].items():
        for key in ['json','signature','stdout','stderr','elf']:
            if probe.get(key) not in artifacts:raise ValueError('Selected CSR raw execution evidence missing')
        run=json.loads((capsule/probe['json']).read_text())
        if (run.get('exit_status')!=0 or run.get('timed_out') is not False or
                run.get('binary_sha256')!=receipt['simulator_binary_sha256'] or
                run.get('elf_sha256')!=artifacts[probe['elf']]):raise ValueError('Selected CSR execution identity/exit mismatch')
        matching=[key for key,row in receipt['origins'].items() if row['path']==run['argv'][0]]
        if len(matching)!=1 or artifacts[matching[0]]!=run['binary_sha256']:
            raise ValueError('Selected CSR executable bytes absent from capsule')
        decoded[name]=decode_signature((capsule/probe['signature']).read_text(),name)
        if name=='rdtime':
            for row in decoded[name]:
                if elf_word(capsule/probe['elf'],row['pc'])!=row['tval']:
                    raise ValueError('CSR time trap PC does not identify tested instruction')
    return {'tested':True,'scope':'initialized zero-HPM CSR masks/RAZ-WI and illegal CSR time on all3 harts',
        'harts':decoded,'source_fir_sha256':receipt['source_fir_sha256'],
        'source_policy_elaboration_sha256':json.loads((ROOT/'spike/reset-hpm-policy.json').read_text())['fir_sha256'],
        'elaboration_relationship':'Separate saved IrisConfig and FireSim elaborations; selected CSR observations agree, full-image equivalence unverified',
        'saved_design':receipt['saved_design'],'rtl_simulator_sha256':receipt['simulator_binary_sha256'],
        'full_rtl_certified':False,'reset_definedness_certified':False,'timing_calibrated':False,
        'matches_ethan_firesim_image':False,'calibration_usable_for_firesim':False},evidence
