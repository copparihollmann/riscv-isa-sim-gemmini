"""Identifying experiments v2; does not alter or fit the frozen v1/held-out sets."""
import struct

KINDS = ['dependent', 'independent', 'frontend', 'branch', 'memory', 'atomic',
         'scalar_fp', 'vector_int', 'vector_fp', 'vme_int', 'vme_fp8',
         'row_read', 'row_write', 'tile_zero', 'vme_memory', 'shared_fpu',
         'pipeline', 'pipeline_vme', 'vme_refusal']


def fpbits(number, width):
    return int.from_bytes(struct.pack({16:'<e',32:'<f',64:'<d'}[width], float(number)), 'little')


def cases():
    result=[]
    def add(name,kind,n=64,mask=7,sew=32,lmul=1,mode=0,size=4096,protocol=0,edge=32,tk=1,tiles=1,expected=0,**metadata):
        row={'case_id':'v2.'+name,'kind':kind,'n':n,'mask':mask,'sew':sew,'lmul':lmul,'mode':mode,
             'bytes':size,'protocol':protocol,'edge':edge,'tk':tk,'tiles':tiles,
             'expected_checksums':expected if isinstance(expected,list) else [expected]*3,
             'region':'kernel','status':'ready','metadata':metadata}
        result.append(row)
    for n in (128,512,2048):
        add(f'scalar.dependent.{n}','dependent',n,expected=1+8*n,scalar_alu_operations=8*n)
        add(f'scalar.independent8.{n}','independent',n,expected=36+8*n,scalar_alu_operations=8*n)
    for footprint in (512,4096,16384):
        for n in (4,16):
            add(f'frontend.{footprint}b.{n}','frontend',n,size=footprint,expected=n*(footprint//4),
                preparation='one full exact-code traversal outside region; no I-cache flush',instruction_body_bytes=footprint)
    for n in (256,1024):
        add(f'branch.taken.{n}','branch',n,mode=0,expected=n,branch_pattern='always taken')
        state=1; golden=0
        for _ in range(n):
            state=((state>>1)^((-(state&1))&0xd0000001))&0xffffffff
            golden+=3 if state&1 else 1
        add(f'branch.lfsr.{n}','branch',n,mode=1,expected=golden,branch_pattern='deterministic 32-bit LFSR seed1')
    for protocol,label in ((1,'warm'),(2,'eviction-attempt')):
        for size in (4096,16384,131072,1048576):
            for mask in (1,3):
                add(f'memory.read.{label}.{size}.mask{mask}','memory',n=2,mask=mask,size=size,protocol=protocol,
                    expected=2*(size//4),read_bytes=2*size,preparation='initialize private target, then '+label)
        for size in (4096,65536,1048576):
            add(f'memory.chase.{label}.{size}','memory',n=4096,mask=3,mode=1,size=size,protocol=protocol,
                expected=(4096*16)%(size//4),read_bytes=4096*4,dependent_loads=4096)
    for size in (4096,1048576):
        for mask in (1,2,4,3,5,6,7):
            add(f'contention.private-read.{size}.mask{mask}','memory',n=2,mask=mask,size=size,protocol=1,
                expected=2*(size//4),read_bytes=2*size,sharing='disjoint per-hart buffers')
        for mask in (1,2,4,3,5,6,7):
            add(f'contention.shared-read.{size}.mask{mask}','memory',n=2,mask=mask,mode=2,size=size,protocol=1,
                expected=2*(size//4),read_bytes=2*size,sharing='same read-only buffer, initialized before batch')
        for mode,engine in ((3,'scalar'),(4,'vector')):
            add(f'contention.read-plus-hart2-{engine}-write.{size}.mask5','memory',n=2,mask=5,mode=mode,size=size,protocol=1,
                expected=2*(size//4),read_bytes_by_hart=[2*size,0,0],write_bytes_by_hart=[0,0,2*size],hart2_writer_engine=engine)
    for mode,label in ((0,'same-counter'),(1,'false-sharing'),(2,'separate-lines')):
        for mask in (1,2,4,3,5,6,7):
            add(f'contention.atomic.{label}.mask{mask}','atomic',n=256,mask=mask,mode=mode,expected=256,
                atomic_operations_per_hart=256,sharing=label)
    for width in (16,32,64):
        for n in (16,64):
            add(f'scalar.fp{width}.add.{n}','scalar_fp',n,sew=width,expected=fpbits(n,width),floating_operations=n)
    for width in (8,16,32,64):
        for lmul in (1,2,4):
            for mode,label in ((0,'dependent'),(1,'independent2')):
                vl=256*lmul//width; n=64; streams=1+mode
                add(f'vector.i{width}.m{lmul}.{label}','vector_int',n,sew=width,lmul=lmul,mode=mode,
                    expected=vl*streams*(1+n),vector_add_operations=n*streams,elements=vl*n*streams)
    for width in (16,32,64):
        for lmul in (1,2):
            for n in (16,64):
                vl=256*lmul//width
                add(f'vector.fp{width}.m{lmul}.add.{n}','vector_fp',n,sew=width,lmul=lmul,
                    expected=(vl*fpbits(n,width))&((1<<64)-1),floating_operations=vl*n)
    for tk in (1,4):
        for n in (0,16,64):
            add(f'vme.int8.tk{tk}.{n}','vme_int',n,mask=3,tk=tk,expected=32*n*tk,macs=32*32*n*tk)
    for tiles,n in ((1,256),(4,64),(4,0)):
        add(f'vme.tile-hazards.tiles{tiles}.{n}','vme_int',n,mask=3,tk=4,tiles=tiles,
            expected=32*n*4*tiles,macs=32*32*n*4*tiles)
    for mode,a,b in ((0,'e4m3','e4m3'),(1,'e5m2','e4m3'),(2,'e4m3','e5m2'),(3,'e5m2','e5m2')):
        for n in (16,64):
            add(f'vme.fp8.{a}.{b}.{n}','vme_fp8',n,mask=3,mode=mode,tk=4,
                expected=32*fpbits(n*4,32),macs=32*32*n*4,input_formats=[a,b],accumulator='f32')
    for kind in ('row_read','row_write','tile_zero'):
        for n in (16,64):
            add(f'vme.{kind}.{n}',kind,n,mask=3,expected=0 if kind=='tile_zero' else 32*7,
                row_transfer_bytes=0 if kind=='tile_zero' else n*128,columns=False)
    for mode,label in ((0,'serial'),(1,'interleaved')):
        n=64
        add('overlap.vme-scalar-loads.'+label,'vme_memory',n,mask=3,mode=mode,tk=4,
            expected=32*n*4+4*n,macs=32*32*n*4,scalar_load_bytes=16*n)
    for mode,label in ((0,'scalar-only'),(1,'vector-only'),(2,'serial'),(3,'interleaved')):
        n=64; count=(1 if mode==0 else 8 if mode==1 else 9)
        add('shared-fpu.hart2.'+label,'shared_fpu',n,mask=4,sew=32,mode=mode,
            expected=count*fpbits(n,32),scalar_fp_operations=n if mode!=1 else 0,
            vector_fp_operations=n*8 if mode!=0 else 0)
    for mask in (1,2,4,3,5,6,7):
        add(f'placement.scalar.dependent.mask{mask}','dependent',128,mask=mask,expected=1025,scalar_alu_operations=1024)
        add(f'placement.scalar.independent.mask{mask}','independent',128,mask=mask,expected=1060,scalar_alu_operations=1024)
        add(f'placement.vector.i32.mask{mask}','vector_int',64,mask=mask,sew=32,expected=8*65,elements=8*64)
        add(f'placement.vector.fp32.mask{mask}','vector_fp',64,mask=mask,sew=32,expected=8*fpbits(64,32),floating_operations=8*64)
    for mask in (1,2):
        for n in (16,64):
            add(f'placement.vme.int8.{n}.mask{mask}','vme_int',n,mask=mask,tk=4,expected=32*n*4,macs=32*32*n*4)
        for mode,a,b in ((0,'e4m3','e4m3'),(1,'e5m2','e4m3'),(2,'e4m3','e5m2'),(3,'e5m2','e5m2')):
            add(f'placement.vme.fp8.{a}.{b}.mask{mask}','vme_fp8',16,mask=mask,mode=mode,tk=4,
                expected=32*fpbits(64,32),macs=32*32*16*4,input_formats=[a,b],accumulator='f32')
    for producer in range(3):
        compute=(producer+1)%3;consumer=(producer+2)%3;expected=[0,0,0]
        expected[producer]=36*16;expected[compute]=expected[consumer]=44*16
        add(f'pipeline.scalar-vector.rotate{producer}','pipeline',16,mode=producer,mask=7,expected=expected,
            producer_hart=producer,compute_hart=compute,consumer_hart=consumer,
            synchronization='monotonic acquire/release phase counter, producer data→vector add→consumer sum')
    for compute in (0,1):
        expected=[0,0,64*8];expected[compute]=expected[1-compute]=32*8
        add(f'pipeline.vme.compute{compute}','pipeline_vme',8,mask=7,mode=compute,expected=expected,
            producer_hart=2,compute_hart=compute,consumer_hart=1-compute,
            synchronization='producer bytes→VME tile compute/readback→consumer sum',macs=8*32*32)
    add('functional.hart2.vme_refusal','vme_refusal',1,mask=4,expected=1,
        expected_exception='illegal_instruction',instruction='sf.vtdiscard')
    return result


PENDING = [
    {'case_id':'v2.pending.vector.bf16.fma','status':'pending','reason':'Needs source-matched native BF16 vector arithmetic certification and a bit-exact guest oracle.'},
    {'case_id':'v2.pending.vector.fp8.e4m3.fma','status':'pending','reason':'Native FP8 vector arithmetic implementation/certification is in progress; VME FP8 cases are separate.'},
    {'case_id':'v2.pending.vector.fp8.e5m2.fma','status':'pending','reason':'Native FP8 vector arithmetic implementation/certification is in progress; VME FP8 cases are separate.'},
    {'case_id':'v2.pending.vector.fp8.bf16.conversions','status':'pending','reason':'Requires explicit rounding/saturation/exception guest oracles before fitting.'},
    {'case_id':'v2.pending.vme.column-read','status':'blocked-by-hardware-audit','reason':'Elaborated OPU lacks column readout; no fabricated flush/column capability is used.'},
]
