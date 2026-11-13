#!/usr/bin/env python3
"""Resolve fatal ELF symbols, then exec the exact SDK4 native model."""
import hashlib
import os
from pathlib import Path
import struct
import sys

HERE=Path(__file__).resolve().parent
NATIVE_SHA='35901887c93ab80aa92e68aac2f26cefa6cc785ae8251d5dc283471aa97faf5d'
FATAL_SYMBOLS={'z_fatal_error','k_sys_fatal_error_handler','arch_system_halt','__assert_func','__stack_chk_fail','abort'}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def fatal_addresses(path):
    data=path.read_bytes()
    def unpack(fmt,offset):
        size=struct.calcsize(fmt)
        if offset<0 or offset+size>len(data):raise ValueError('truncated ELF structure')
        return struct.unpack_from(fmt,data,offset)
    h=unpack('<16sHHIQQQIHHHHHH',0)
    if h[0][:7]!=b'\x7fELF\x02\x01\x01'or h[2]!=243:raise ValueError('RV64 little-endian ELF required')
    if h[11]!=64 or h[12]==0:raise ValueError('ELF section table required for fatal symbol resolution')
    sections=[unpack('<IIQQQQIIQQ',h[6]+i*h[11])for i in range(h[12])]
    if not any(row[1]==2 for row in sections):raise ValueError('unstripped ELF symbol table required for fatal-handler resolution')
    def section(row):
        start,size=row[4],row[5]
        if start>len(data)or size>len(data)-start:raise ValueError('truncated ELF section')
        return data[start:start+size]
    found={}
    for row in sections:
        if row[1]not in(2,11):continue
        if row[9]!=24 or row[5]%24 or row[6]>=len(sections):raise ValueError('invalid ELF symbol table')
        table=section(row);strings=section(sections[row[6]])
        for offset in range(0,len(table),24):
            name,info,other,index,value,size=struct.unpack_from('<IBBHQQ',table,offset)
            if name>=len(strings):raise ValueError('invalid ELF symbol name')
            end=strings.find(b'\0',name)
            if end<0:raise ValueError('unterminated ELF symbol name')
            text=strings[name:end].decode('utf-8',errors='strict')
            if text in FATAL_SYMBOLS and index and value and info&15 in(0,2):found[text]=value
    return found

def main():
    native=HERE/'bin/spike'
    if not native.is_file()or sha(native)!=NATIVE_SHA:raise ValueError('exact SDK4 native binary missing or changed')
    if len(sys.argv)<2:raise ValueError('guest ELF argument required')
    # Merlin supplies one ELF after atomic Spike options, with no guest args.
    # Accept the same form explicitly; avoid guessing a different input file.
    elf=Path(sys.argv[-1]).resolve()
    if not elf.is_file():raise ValueError('last argument must be the guest ELF')
    before=sha(elf);symbols=fatal_addresses(elf)
    configured=set(symbols.values())
    raw=os.environ.get('IRIS_FATAL_PCS','')
    if raw:
        for token in raw.split(','):
            value=int(token,0)
            if value<0 or value>=1<<64:raise ValueError('invalid explicit fatal PC')
            configured.add(value)
    environment=dict(os.environ)
    if configured:environment['IRIS_FATAL_PCS']=','.join(hex(value)for value in sorted(configured))
    if sha(elf)!=before or sha(native)!=NATIVE_SHA:raise ValueError('execution input changed before native exec')
    os.execve(str(native),[str(native),*sys.argv[1:]],environment)
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,UnicodeError,struct.error)as error:
        print('IRIS_LAUNCH_REFUSED: '+str(error),file=sys.stderr);sys.exit(1)
