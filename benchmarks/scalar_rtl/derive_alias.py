#!/usr/bin/env python3
"""Version a read-only-alias control by changing only eight CSR-address bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--parent',type=Path,default=ROOT/'build/scalar-rtl-probe-v1/build.json')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();parent=json.loads(a.parent.read_text());elf=Path(parent['elf'])
    if sha(elf)!=parent['elf_sha256']:raise ValueError('parent ELF changed')
    for path,digest in parent['input_sha256'].items():
        if sha(path)!=digest:raise ValueError('parent build source changed '+path)
    raw=bytearray(elf.read_bytes());before=bytes(raw);phoff=struct.unpack_from('<Q',raw,32)[0];phsize,phnum=struct.unpack_from('<HH',raw,54)
    changes=[]
    for i in range(phnum):
        typ,flags,off,va,pa,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',raw,phoff+i*phsize)
        if typ!=1 or not(flags&1):continue
        cursor=0
        while cursor+2<=filesz:
            low=struct.unpack_from('<H',raw,off+cursor)[0];length=2 if low&3!=3 else 4
            if cursor+length>filesz:break
            if length==4:
                word=struct.unpack_from('<I',raw,off+cursor)[0];csr=word>>20
                if word&127==0x73 and csr in (0xB00,0xB02):
                    if (word>>12)&7!=2 or (word>>15)&31 or (word>>7)&31 not in (11,29,30,31):raise ValueError('unexpected counter read form')
                    updated=word+(0x100<<20);struct.pack_into('<I',raw,off+cursor,updated)
                    changes.append({'pc':va+cursor,'file_offset':off+cursor,'old_instruction':word,'new_instruction':updated})
            cursor+=length
    if len(changes)!=8 or sum(c['old_instruction']>>20==0xB00 for c in changes)!=4:raise ValueError('exactly four B00 and four B02 instruction sites required')
    differences=[i for i,(old,new) in enumerate(zip(before,raw)) if old!=new]
    if len(differences)!=8 or sorted(differences)!=sorted(c['file_offset']+3 for c in changes):raise ValueError('derivation changed more than CSR address bytes')
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);target=out/'scalar-readonly-alias.elf';target.write_bytes(raw)
    receipt={**parent,'elf':str(target),'elf_sha256':sha(target),'parent_build_sha256':sha(a.parent),'parent_elf_sha256':sha(elf),
             'derivation':'B00/B02 -> C00/C02 CSRRS x0 address fields only; same addresses/body/ELF symbols/DWARF bytes',
             'instruction_changes':changes,'file_byte_changes':differences,'source_counter_expectation':'257 visible minstret delta on all three harts; read-only aliases do not write counter state'}
    receipt['input_sha256']={**parent['input_sha256'],str(a.parent.resolve()):sha(a.parent),str(elf):sha(elf),str(Path(__file__).resolve()):sha(Path(__file__))}
    (out/'inputs').mkdir()
    for path,digest in receipt['input_sha256'].items():
        destination=out/'inputs'/digest
        if not destination.exists():shutil.copyfile(path,destination)
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n');print(target)


if __name__=='__main__':main()
