#!/usr/bin/env python3
"""Read a pinned DCP's V37 chunked-ZSTD EDIF without vendor hardware access."""
import argparse
import ctypes
import ctypes.util
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import zipfile


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


class Buffer(ctypes.Structure):
    _fields_=[('data',ctypes.c_void_p),('size',ctypes.c_size_t),('pos',ctypes.c_size_t)]


class Zstd:
    def __init__(self):
        name=ctypes.util.find_library('zstd')
        if not name:raise ValueError('Installed libzstd is required')
        self.lib=ctypes.CDLL(name);lib=self.lib
        lib.ZSTD_createDStream.restype=ctypes.c_void_p
        lib.ZSTD_freeDStream.argtypes=[ctypes.c_void_p];lib.ZSTD_freeDStream.restype=ctypes.c_size_t
        lib.ZSTD_initDStream.argtypes=[ctypes.c_void_p];lib.ZSTD_initDStream.restype=ctypes.c_size_t
        lib.ZSTD_decompressStream.argtypes=[ctypes.c_void_p,ctypes.POINTER(Buffer),ctypes.POINTER(Buffer)]
        lib.ZSTD_decompressStream.restype=ctypes.c_size_t
        lib.ZSTD_isError.argtypes=[ctypes.c_size_t];lib.ZSTD_isError.restype=ctypes.c_uint
        lib.ZSTD_getErrorName.argtypes=[ctypes.c_size_t];lib.ZSTD_getErrorName.restype=ctypes.c_char_p
        lib.ZSTD_versionString.restype=ctypes.c_char_p
        self.version=lib.ZSTD_versionString().decode('ascii')
        self.context=lib.ZSTD_createDStream()
        if not self.context:raise MemoryError('Could not construct ZSTD stream')
        self.check(lib.ZSTD_initDStream(self.context))

    def check(self,value):
        if self.lib.ZSTD_isError(value):raise ValueError(self.lib.ZSTD_getErrorName(value).decode('ascii'))
        return value

    def decode(self,data,expected):
        source=ctypes.create_string_buffer(data);target=ctypes.create_string_buffer(expected+1)
        a=Buffer(ctypes.addressof(source),len(data),0);b=Buffer(ctypes.addressof(target),len(target),0)
        while a.pos<a.size:
            before=(a.pos,b.pos)
            self.remaining=self.check(self.lib.ZSTD_decompressStream(self.context,ctypes.byref(b),ctypes.byref(a)))
            if before==(a.pos,b.pos)or b.pos>expected:raise ValueError('Chunk made no progress or exceeded declared output')
        if b.pos!=expected:raise ValueError('Decoded chunk size does not match wrapper header')
        return target.raw[:b.pos]

    def close(self):
        if self.context:self.lib.ZSTD_freeDStream(self.context);self.context=None


class LexicalBalance:
    def __init__(self):self.depth=0;self.quoted=False;self.escaped=False;self.opens=0
    def accept(self,data):
        for byte in data:
            if byte<32 and byte not in(9,10,13):raise ValueError('Non-text control byte in decoded EDIF')
            if self.quoted:
                if self.escaped:self.escaped=False
                elif byte==92:self.escaped=True
                elif byte==34:self.quoted=False
            elif byte==34:self.quoted=True
            elif byte==40:self.depth+=1;self.opens+=1
            elif byte==41:
                self.depth-=1
                if self.depth<0:raise ValueError('Unbalanced EDIF expression')
    def finish(self):
        if self.depth or self.quoted or self.escaped or not self.opens:
            raise ValueError('Incomplete EDIF expressions/strings')


def extract(checkpoint,expected,member,output,max_bytes=8*1024**3):
    if output.exists():raise ValueError('Fresh extraction directory required')
    if not re.fullmatch('[0-9a-f]{64}',expected)or digest(checkpoint)!=expected:
        raise ValueError('Exact checkpoint digest required')
    output.mkdir(parents=True);started=time.monotonic()
    report={'schema':'iris.checkpoint_offline_edif_decode.v1','status':'running','checkpoint':str(checkpoint),
        'checkpoint_sha256':expected,'member':member,'source_sha256':digest(Path(__file__)),
        'python_sha256':digest(Path(sys.executable).resolve()),'hardware_contacted':False,
        'INIT_values_certified':False,'loaded_image_association_certified':False,'max_output_bytes':max_bytes}
    decoder=None
    try:
        decoder=Zstd();report['libzstd_version']=decoder.version
        libraries={Path(line.split(maxsplit=5)[-1])for line in Path('/proc/self/maps').read_text().splitlines()
                   if len(line.split(maxsplit=5))==6 and '/libzstd.so'in line.split(maxsplit=5)[-1]}
        if len(libraries)!=1:raise ValueError('Unique loaded libzstd identity required')
        library=libraries.pop();report['libzstd']={'path':str(library),'sha256':digest(library)}
        compressed=hashlib.sha256();plain=hashlib.sha256();chunks=total=0;balance=LexicalBalance()
        with zipfile.ZipFile(checkpoint)as archive:
            if archive.namelist().count(member)!=1:raise ValueError('Unique exact EDIF archive member required')
            info=archive.getinfo(member);report['member_bytes']=info.file_size
            with archive.open(member)as source,(output/'netlist.edf').open('xb')as target:
                while True:
                    header=source.read(24)
                    if not header:break
                    if len(header)!=24 or header[:8]!=b'XlxV37EB':
                        raise ValueError('Unsupported/truncated chunk wrapper: '+repr(header[:8]))
                    if not re.fullmatch(b'[ 0-9a-fA-F]{16}',header[8:]):raise ValueError('Invalid chunk lengths')
                    amount=int(header[8:16],16);size=int(header[16:24],16)
                    if not 0<=amount<=2**20 or not 0<size<=4*2**20 or total+amount>max_bytes:
                        raise ValueError('Chunk/extraction size bound exceeded')
                    block=source.read(size)
                    if len(block)!=size:raise ValueError('Truncated compressed chunk')
                    compressed.update(header);compressed.update(block)
                    decoded=decoder.decode(block,amount)
                    if chunks==0 and not decoded.startswith(b'(edif '):raise ValueError('Decoded file is not EDIF text')
                    balance.accept(decoded);target.write(decoded);plain.update(decoded);total+=len(decoded);chunks+=1
        balance.finish()
        if digest(checkpoint)!=expected:raise ValueError('Checkpoint changed during extraction')
        report.update(status='decoded_text_and_lexical_balance_verified',chunks=chunks,decoded_bytes=total,
            compressed_member_sha256=compressed.hexdigest(),decoded_edif_sha256=plain.hexdigest(),
            parenthesized_expressions=balance.opens,zstd_frame_remainder=decoder.remaining,
            scope='Every wrapper length, decoded chunk size, ZIP CRC, checkpoint digest and lexical expression/string balance checked. Full EDIF semantics and primitive INIT mapping require separate validation.')
    except(OSError,ValueError,KeyError,zipfile.BadZipFile,MemoryError)as error:
        report.update(status='failed',error=str(error))
    finally:
        if decoder:decoder.close()
    report['host_seconds']=time.monotonic()-started
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report.get(k)for k in('status','chunks','decoded_bytes','decoded_edif_sha256','error','host_seconds')}))
    return 0 if report['status']=='decoded_text_and_lexical_balance_verified'else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--sha256',required=True);p.add_argument('--member',default='overall_fpga_top.edf')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--max-output-bytes',type=int,default=8*1024**3)
    a=p.parse_args();raise SystemExit(extract(a.checkpoint.resolve(),a.sha256,a.member,a.output.resolve(),a.max_output_bytes))
