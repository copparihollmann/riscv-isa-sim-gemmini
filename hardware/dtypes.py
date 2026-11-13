#!/usr/bin/env python3
"""Generate/verify a source-bound Iris dtype audit, separate from model support."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = Path('/scratch/eygao/iris-cy')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def scalar_bf16_decoder_proof(text, custom_text):
    patterns = []
    counts = {}
    for identity, content, expected in [('scalar-instructions', text, 807), ('custom-instructions', custom_text, 28)]:
        found = re.findall(r'def\s+(\w+)\s*=\s*BitPat\("b([01?]{32})"\)', content)
        if len(found) != expected:
            raise ValueError('pinned scalar instruction pattern set changed; re-audit BF16 decode')
        counts[identity] = len(found)
        for name, bits in found:
            patterns.append((name, int(bits.replace('?', '0'), 2),
                             int(''.join('0' if bit == '?' else '1' for bit in bits), 2)))
    cases = []
    for name, value in [('fcvt.bf16.s', 0x44800053), ('fcvt.s.bf16', 0x40600053)]:
        mask = 0xfff0007f
        intersections = [n for n, v, m in patterns if not ((v ^ value) & m & mask)]
        if intersections:
            raise ValueError('scalar BF16 opcode intersects decoder definitions: ' + repr(intersections))
        cases.append({'instruction': name, 'value': hex(value), 'mask': hex(mask),
                      'intersections': [], 'result': 'no-scalar-decoder-entry'})
    return {'all_instruction_patterns': len(patterns), 'pattern_counts': counts, 'cases': cases,
            'sources': ['scalar-instructions', 'custom-instructions'], 'rtl_executed': False}


def verify(data, directory=HERE, live_root=None):
    if data.get('schema_version') != 1 or data.get('scope') != 'hardware-source-audit':
        raise ValueError('unsupported dtype audit schema')
    contents = {}
    for identity, repo in data['repositories'].items():
        if 'tracked_diff' in repo:
            if digest((directory / repo['tracked_diff']).read_bytes()) != repo['tracked_diff_sha256']:
                raise ValueError('repository patch digest mismatch: ' + identity)
    for identity, source in data['sources'].items():
        repo = data['repositories'][source['repository']]
        if not re.fullmatch('[0-9a-f]{40}', source['commit']) or source['commit'] != repo['commit']:
            raise ValueError('source commit mismatch: ' + identity)
        content = (directory / source['snapshot']).read_bytes()
        if digest(content) != source['sha256']:
            raise ValueError('snapshot digest mismatch: ' + identity)
        text = content.decode()
        for token in source.get('required_substrings', []):
            if token not in text:
                raise ValueError('required source anchor missing: ' + identity + ': ' + token)
        contents[identity] = text.splitlines()
        if live_root is not None:
            actual = (live_root / source['path']).read_bytes()
            if digest(actual) != source.get('original_sha256', source['sha256']):
                raise ValueError('live source has changed: ' + identity)
    if 'scalar-instructions' in contents:
        proof = scalar_bf16_decoder_proof('\n'.join(contents['scalar-instructions']), '\n'.join(contents['custom-instructions']))
        if data.get('scalar_bf16_decoder_proof') != proof:
            raise ValueError('scalar BF16 decoder absence proof is stale')
    identifiers = set()
    for row in data['capabilities']:
        if row['id'] in identifiers:
            raise ValueError('duplicate capability id')
        identifiers.add(row['id'])
        if type(row['hart']) is not int or row['hart'] not in (0, 1, 2):
            raise ValueError('invalid hart')
        if row['status'] not in ('configured', 'not_configured', 'unverified'):
            raise ValueError('invalid capability status')
        if not row['evidence']:
            raise ValueError('capability without source evidence')
        for ref in row['evidence']:
            first, last = ref['lines']
            if first < 1 or last < first or last > len(contents[ref['source']]):
                raise ValueError('invalid source line interval: ' + row['id'])
        for dtype in row['input_types'] + row['output_types'] + ([row['accumulator_type']] if row['accumulator_type'] else []):
            if dtype not in data['types']:
                raise ValueError('unknown canonical dtype: ' + dtype)
    return {'source_count': len(contents), 'capability_count': len(identifiers),
            'source_validation_passed': True, 'bitstream_match_verified': False,
            'model_support_certified': False}


def generate(root, directory):
    manifest = json.loads((directory / 'manifest.json').read_text())
    repositories = {key: manifest['repositories'][key] for key in ('chipyard', 'saturn', 'rocket-chip', 'shuttle')}
    hardfloat_path = root / 'generators/hardfloat'
    git_base = ['git', '-c', 'safe.directory=' + str(hardfloat_path), '-C', str(hardfloat_path)]
    hardfloat_commit = subprocess.check_output(git_base + ['rev-parse', 'HEAD']).decode().strip()
    hardfloat_diff = subprocess.check_output(git_base + ['diff', '--binary', 'HEAD'])
    repositories['hardfloat'] = {'commit': hardfloat_commit, 'tracked_modified': bool(hardfloat_diff),
                                 'tracked_diff_sha256': digest(hardfloat_diff), 'local_path': str(hardfloat_path),
                                 'tracked_diff': 'dtypes-evidence/hardfloat.patch'}
    evidence_dir = directory / 'dtypes-evidence'
    evidence_dir.mkdir(exist_ok=True)
    (evidence_dir / 'hardfloat.patch').write_bytes(hardfloat_diff)
    sources = {}

    def source(identity, path, repository, tokens=()):
        raw = (root / path).read_bytes()
        name = 'dtypes-evidence/' + identity + Path(path).suffix
        (directory / name).write_bytes(raw)
        sources[identity] = {'path': path, 'repository': repository, 'commit': repositories[repository]['commit'],
                             'sha256': digest(raw), 'snapshot': name, 'required_substrings': list(tokens),
                             'association': 'local working-tree file; bytes identified independently of repository dirty status'}

    source('iris', 'generators/chipyard/src/main/scala/config/IrisConfigs.scala', 'chipyard',
           ('VectorParams.opuMxParams', 'VectorParams.dmaParams'))
    source('saturn-params', 'generators/saturn/src/main/scala/common/Parameters.scala', 'saturn',
           ('useMxOPU = true', 'useOpuColReadout: Boolean = false', 'case object Unified'))
    source('shuttle-core', 'generators/shuttle/src/main/scala/common/Parameters.scala', 'shuttle', ('FPUParams(minFLen = 16',))
    source('shuttle-vec', 'generators/saturn/src/main/scala/shuttle/Configs.scala', 'saturn', ('vfLen = 64', 'vfh = true'))
    source('rocket-vec', 'generators/saturn/src/main/scala/rocket/Configs.scala', 'saturn', ('minFLen = 16', 'vfLen = 64'))
    source('rocket-core', 'generators/rocket-chip/src/main/scala/rocket/RocketCore.scala', 'rocket-chip', ('fpu: Option[FPUParams] = Some(FPUParams())',))
    source('rocket-big', 'generators/rocket-chip/src/main/scala/rocket/Configs.scala', 'rocket-chip', ('class WithNBigCores',))
    source('fpu', 'generators/rocket-chip/src/main/scala/tile/FPU.scala', 'rocket-chip',
           ('fLen: Int = 64', 'case (16, 64) => h ++ f ++ d ++ fcvt_hd'))
    source('csr', 'generators/rocket-chip/src/main/scala/rocket/CSR.scala', 'rocket-chip', ('val altfmt = Bool()',))
    source('int-decode', 'generators/rocket-chip/src/main/scala/rocket/IDecode.scala', 'rocket-chip')
    source('scalar-instructions', 'generators/rocket-chip/src/main/scala/rocket/Instructions.scala', 'rocket-chip')
    source('custom-instructions', 'generators/rocket-chip/src/main/scala/rocket/CustomInstructions.scala', 'rocket-chip')
    source('shuttle-exec', 'generators/shuttle/src/main/scala/exu/Core.scala', 'shuttle', ('rrd_illegal_insn(i) := (!ctrl.legal',))
    source('mx-types', 'generators/saturn/src/main/scala/exu/fp/MXFType.scala', 'saturn', ('val BF16 = new FType(8, 8)',))
    source('fma', 'generators/saturn/src/main/scala/exu/fp/FPFMAPipe.scala', 'saturn', ('rawUnroundedToFp8', 'MXFType.BF16'))
    source('shared-fma', 'generators/saturn/src/main/scala/exu/fp/SharedFPFMA.scala', 'saturn', ('base_insns.map(_.elementWise)',))
    source('fp-conv', 'generators/saturn/src/main/scala/exu/fp/FPConv.scala', 'saturn', ('if (mxConversion)', 'fp82bf16', 'bf162s'))
    source('fp-div', 'generators/saturn/src/main/scala/exu/fp/FPDiv.scala', 'saturn', ('restrictSEW(1,2,3)',))
    source('fp-comp', 'generators/saturn/src/main/scala/exu/fp/FPComp.scala', 'saturn', ('Seq(FType.H, FType.S, FType.D)',))
    source('fp8-expand', 'generators/saturn/src/main/scala/exu/fp/fp8ToE5M3.scala', 'saturn', ('val isNaN = exp.andR && sig.andR',))
    source('fp8-narrow', 'generators/saturn/src/main/scala/exu/fp/e5M3ToFp8.scala', 'saturn', ('object assembleOFPE4M3',))
    source('opu', 'generators/saturn/src/main/scala/exu/OuterProductUnit.scala', 'saturn', ('if (useMxOPU)', 'fma.io.roundingMode := io.rm.get'))
    source('opu-seq', 'generators/saturn/src/main/scala/backend/OuterProductSequencer.scala', 'saturn', ('signed_t := dis_inst.vconfig.vtype.altfmt',))
    source('backend', 'generators/saturn/src/main/scala/backend/Backend.scala', 'saturn', ('if (useOpuColReadout)',))
    source('issue-queue', 'generators/saturn/src/main/scala/backend/IssueQueue.scala', 'saturn', ('io.deq <> io.enq',))
    source('early-decode', 'generators/saturn/src/main/scala/frontend/EarlyDecode.scala', 'saturn', ('io.fp := funct3 === OPFVF',))
    source('int-div', 'generators/saturn/src/main/scala/exu/int/IntegerDivide.scala', 'saturn', ('if (supportsMul) mulInsns else Nil',))
    source('int-mul', 'generators/saturn/src/main/scala/exu/int/SegmentedMultiplyPipe.scala', 'saturn')
    source('int-alu', 'generators/saturn/src/main/scala/exu/int/IntegerPipe.scala', 'saturn')
    source('hardfloat-round', 'generators/hardfloat/hardfloat/src/main/scala/RoundAnyRawFNToRecFN.scala', 'hardfloat', ('val signOut = Mux(isNaNOut, false.B, io.in.sign)',))
    source('hardfloat-convert', 'generators/hardfloat/hardfloat/src/main/scala/RecFNToRecFN.scala', 'hardfloat')
    source('hardfloat-fma', 'generators/hardfloat/hardfloat/src/main/scala/MulAddRecFN.scala', 'hardfloat')
    source('dts', 'sims/firesim-staging/generated-src/firechip.chip.FireSim.IrisFiresimNOCflushCombinedConfig/firechip.chip.FireSim.IrisFiresimNOCflushCombinedConfig.dts', 'chipyard')

    fir = manifest['sources']['firesim-fir']
    wanted = (('module OuterProductCluster :', 4), ('module OuterProductUnit :', 4))
    excerpt = []
    ranges = []
    with (root / fir['path']).open() as inp:
        remaining = 0
        for number, line in enumerate(inp, 1):
            for token, count in wanted:
                if line.strip().startswith(token):
                    remaining = count
                    ranges.append({'snapshot_start_line': len(excerpt) + 1, 'original_start_line': number, 'line_count': count})
                    break
            if remaining:
                excerpt.append(line)
                remaining -= 1
    if len(excerpt) != 8:
        raise ValueError('missing elaborated OPU port definitions')
    raw = ''.join(excerpt).encode()
    name = 'dtypes-evidence/fir-opu-ports.txt'
    (directory / name).write_bytes(raw)
    sources['fir-opu-ports'] = {'path': fir['path'], 'repository': 'chipyard', 'commit': repositories['chipyard']['commit'],
                               'original_sha256': fir['sha256'], 'sha256': digest(raw), 'snapshot': name,
                               'original_line_ranges': ranges, 'required_substrings': ['flip fp8', 'flip e5m2_l', 'out : UInt<32>[4]'],
                               'association': 'local elaboration; exact build source identity and deployed image match remain unverified'}

    def ref(identity, first, last):
        return {'source': identity, 'lines': [first, last]}

    rows = []

    def row(hart, name, unit, inputs, outputs, operations, status='configured', accumulator=None,
            widths=(), refs=(), notes=(), **extra):
        rows.append({'id': 'hart' + str(hart) + '.' + unit + '.' + name, 'hart': hart, 'unit': unit,
                     'input_types': list(inputs), 'accumulator_type': accumulator, 'output_types': list(outputs),
                     'operations': list(operations), 'status': status, 'execution_width_bits': list(widths),
                     'evidence': list(refs), 'notes': list(notes), **extra})

    ints = ['i8', 'u8', 'i16', 'u16', 'i32', 'u32', 'i64', 'u64']
    fp = ['f16', 'f32', 'f64']
    fp8 = ['ofp8_e4m3', 'ofp8_e5m2']
    config_refs = [ref('iris', 277, 301), ref('saturn-params', 71, 110), ref('saturn-params', 358, 395)]
    for hart in range(3):
        compute = hart < 2
        mx_status = 'configured' if compute else 'not_configured'
        scalar_refs = [ref('shuttle-core', 39, 45)] if compute else [ref('rocket-big', 62, 81), ref('rocket-core', 56, 56), ref('rocket-vec', 44, 49)]
        scalar_refs += [ref('fpu', 17, 24), ref('fpu', 64, 173)]
        row(hart, 'narrow-integers', 'scalar', ints[:4], ints, ['load_store', 'promoted_arithmetic'], widths=[32, 64],
            refs=[ref('int-decode', 40, 130)], notes=['8/16-bit storage and sign/zero extension; arithmetic uses 32/64-bit registers, not native narrow ALUs.'])
        row(hart, 'native-integers', 'scalar', ints[4:], ints[4:], ['load_store', 'add', 'sub', 'mul', 'div', 'rem', 'shift', 'bitwise', 'compare', 'amo_lrsc'], widths=[32, 64],
            refs=[ref('int-decode', 71, 130), ref('int-decode', 214, 305)], notes=['RV64 word operations and extension/truncation rules apply; unsigned 32-bit values may need zero extension.'])
        row(hart, 'ieee-floating', 'scalar', fp, fp, ['load_store', 'convert', 'add', 'sub', 'mul', 'fma', 'div', 'sqrt', 'compare', 'minmax', 'classify'], widths=[16, 32, 64], refs=scalar_refs,
            notes=['Full H/S/D decode, including half arithmetic; this is stronger than Zfhmin-only support. Conversion pairs follow the individual instructions, not an arbitrary Cartesian product.'])
        row(hart, 'minifloat-storage', 'scalar', ['bf16'] + fp8, ['bf16'] + fp8, ['load_store_bits'], widths=[8, 16], refs=[ref('int-decode', 40, 130)],
            notes=['Bit transport through integer loads/stores does not imply floating arithmetic.'])
        row(hart, 'bf16-convert', 'scalar', ['bf16', 'f32'], ['bf16', 'f32'], ['convert'], status='not_configured', refs=[ref('dts', 18 if compute else 74, 44 if compute else 103), ref('fpu', 64, 173), ref('scalar-instructions', 12, 818), ref('custom-instructions', 8, 38), ref('shuttle-exec', 243, 263), ref('early-decode', 36, 70)],
            notes=['Compute DTS advertises Zfbfmin, but both scalar BF16 encodings are disjoint from all 807 Rocket Instructions.scala and 28 CustomInstructions.scala patterns. Scalar/FPU decoders select only those definitions; Saturn vector EarlyDecode excludes scalar opcode 0x53. The source therefore has no executable scalar BF16 conversion path, despite the advertisement. Exact deployed-image association remains unverified.'] if compute else ['No Zfbfmin advertisement; both scalar BF16 encodings miss all 835 normal/custom scalar decoder patterns. Vector BF16/FP8 storage does not establish scalar conversion support.'])
        row(hart, 'bf16-arithmetic', 'scalar', ['bf16'], ['bf16'], ['add', 'sub', 'mul', 'fma', 'div', 'sqrt'], status='not_configured', refs=[ref('fpu', 64, 173)], notes=['No native BF16 scalar arithmetic path in the reviewed FPU.'])
        row(hart, 'fp8-arithmetic', 'scalar', fp8, fp8, ['add', 'sub', 'mul', 'fma', 'convert'], status='not_configured', refs=[ref('fpu', 64, 173)], notes=['FP8 hardware is in vector/VME units, not the scalar FPU.'])
        row(hart, 'int4', 'scalar', ['i4', 'u4'], ['i4', 'u4'], ['arithmetic'], status='not_configured', refs=[ref('int-decode', 40, 130)], notes=['Packed int4 can be manipulated in software; no native 4-bit scalar arithmetic is claimed.'])

        vector_refs = config_refs + [ref('saturn-params', 161, 192), ref('backend', 53, 72), ref('issue-queue', 20, 46)]
        row(hart, 'integer-arithmetic', 'vector', ints, ints, ['load_store', 'add', 'sub', 'mul', 'mac', 'div', 'rem', 'shift', 'bitwise', 'compare'], widths=[8, 16, 32, 64], refs=vector_refs + [ref('int-div', 13, 39), ref('int-alu', 177, 210), ref('int-mul', 12, 28)],
            notes=['Hart 2 uses iterative integer multiply/divide; its zero-depth execute queue bypasses storage and does not remove arithmetic.'] if not compute else ['DLEN 128 vector datapath; supported operation variants follow decoder definitions.'])
        row(hart, 'integer-widen', 'vector', ints[:6], ints[2:], ['widen_mul', 'widen_mac'], widths=[16, 32, 64], refs=[ref('int-mul', 12, 28), ref('int-div', 13, 28)],
            notes=['Input widths 8/16/32 widen to 16/32/64; no 64-to-128 widening operation.'])
        row(hart, 'int4', 'vector', ['i4', 'u4'], ['i4', 'u4'], ['arithmetic'], status='not_configured', refs=[ref('csr', 383, 390)], notes=['Minimum vector element width is 8 bits; packed 4-bit values require software unpacking.'])
        fma_refs = vector_refs + ([ref('fma', 387, 417), ref('fma', 437, 449)] if compute else [ref('shared-fma', 12, 14), ref('shared-fma', 55, 56), ref('shared-fma', 74, 106)])
        row(hart, 'ieee-fma', 'vector', fp, fp, ['add', 'sub', 'mul', 'fma', 'reduce_sum'], widths=[16, 32, 64], refs=fma_refs,
            notes=['Compute has segmented SIMD FP16/32/64; default useElementwiseFP64=false makes every 64-bit lane support double precision.'] if compute else ['Shared scalar FPU executes vector FP16/32/64 elementwise despite the dmaParams memcpy-only comment.'])
        row(hart, 'ieee-misc', 'vector', fp, fp, ['div', 'sqrt', 'recip_estimate', 'rsqrt_estimate', 'classify', 'compare', 'minmax', 'sign_inject'], widths=[16, 32, 64], refs=vector_refs + [ref('fp-div', 230, 240), ref('fp-comp', 12, 20)], notes=['Divide/sqrt are elementwise iterative; compare/minmax have H/S/D formats only.'])
        row(hart, 'ieee-convert', 'vector', fp, fp, ['convert'], widths=[16, 32, 64], refs=[ref('fp-conv', 13, 19), ref('fp-conv', 275, 307)], notes=['Adjacent IEEE widths: FP16↔FP32 and FP32↔FP64; no claim of arbitrary direct width conversion.'])
        row(hart, 'ieee-integer-convert', 'vector', ['i16', 'u16', 'i32', 'u32', 'i64', 'u64'] + fp, ['i16', 'u16', 'i32', 'u32', 'i64', 'u64'] + fp, ['integer_float_convert'], widths=[16, 32, 64], refs=[ref('fp-conv', 84, 147), ref('fp-conv', 250, 274)], notes=['Width, signedness, widening/narrowing and rounding restrictions follow each individual conversion; no BF16/FP8-to-integer conversion is claimed.'])
        for input_t, output_t in [('f16', 'f32'), ('f32', 'f64')]:
            row(hart, 'widen-' + input_t, 'vector', [input_t], [output_t], ['widen_add', 'widen_sub', 'widen_mul', 'widen_fma'], accumulator=output_t, widths=[int(output_t[1:])], refs=fma_refs)
        row(hart, 'minifloat-storage', 'vector', ['bf16'] + fp8, ['bf16'] + fp8, ['load_store_bits'], widths=[8, 16], refs=[ref('early-decode', 36, 70)], notes=['Storage of bit patterns is available independent of Mx arithmetic.'])
        row(hart, 'bf16-fma', 'vector', ['bf16'], ['bf16'], ['add', 'sub', 'mul', 'fma', 'reduce_sum'], status=mx_status, accumulator='bf16', widths=[16], refs=config_refs + [ref('fma', 185, 204), ref('fma', 237, 259), ref('fma', 349, 368)], notes=['Requires the compute Mx FMA path and altfmt=1 at SEW16; does not imply BF16 divide/compare.'])
        row(hart, 'bf16-widen-fma', 'vector', ['bf16'], ['f32'], ['widen_add', 'widen_sub', 'widen_mul', 'widen_fma'], status=mx_status, accumulator='f32', widths=[32], refs=config_refs + [ref('fma', 164, 174), ref('fma', 237, 259)])
        row(hart, 'bf16-convert', 'vector', ['bf16', 'f32'], ['bf16', 'f32'], ['convert'], status=mx_status, widths=[16, 32], refs=config_refs + [ref('fp-conv', 150, 159), ref('fp-conv', 275, 307), ref('fp-conv', 324, 352)])
        row(hart, 'fp8-fma', 'vector', fp8, fp8, ['add', 'sub', 'mul', 'fma', 'reduce_sum'], status=mx_status, widths=[8], refs=config_refs + [ref('fma', 188, 204), ref('fma', 245, 259), ref('fma', 349, 355), ref('fp8-narrow', 41, 46)], notes=['altfmt selects one common FP8 format for vector operands; E4M3 result flags are explicitly zero in rawUnroundedToFp8. This source capability exceeds what the min extension name alone establishes.'] if compute else ['FMA decode may match SEW8, but shared scalar datapath has only H/S/D; do not equate decode acceptance with FP8 arithmetic.'])
        row(hart, 'fp8-widen-fma', 'vector', fp8, ['bf16'], ['widen_add', 'widen_sub', 'widen_mul', 'widen_fma'], status=mx_status, accumulator='bf16', widths=[16], refs=config_refs + [ref('fma', 164, 190), ref('fma', 237, 259)], notes=['Widening SEW8 output is BF16, not a direct FP32 VME-style accumulator.'])
        row(hart, 'fp8-bf16-convert', 'vector', fp8 + ['bf16'], fp8 + ['bf16'], ['convert'], status=mx_status, widths=[8, 16], refs=config_refs + [ref('fp-conv', 150, 159), ref('fp-conv', 289, 312), ref('fp8-expand', 8, 29)])
        row(hart, 'minifloat-misc', 'vector', ['bf16'] + fp8, ['bf16'] + fp8, ['div', 'sqrt', 'compare', 'minmax', 'integer_float_convert'], status='not_configured', refs=[ref('fp-div', 230, 238), ref('fp-comp', 12, 20), ref('fp-comp', 41, 50), ref('fp-conv', 84, 95)], notes=['Reviewed non-FMA units interpret H/S/D only; accepted encodings at an altfmt are not proof of BF16 semantics.'])

        row(hart, 'int8-mac', 'vme', ['i8', 'u8'], ['i32'], ['mac'], status=mx_status, accumulator='i32', widths=[32], refs=config_refs + [ref('opu', 19, 24), ref('opu', 71, 78), ref('opu-seq', 136, 145)],
            input_type_pairs=[['i8', 'i8'], ['i8', 'u8'], ['u8', 'i8'], ['u8', 'u8']], notes=['32-bit accumulator bit pattern wraps modulo 2^32; A signedness is rd bit0, B signedness is altfmt.'])
        row(hart, 'fp8-mac', 'vme', fp8, ['f32'], ['mac'], status=mx_status, accumulator='f32', widths=[32], refs=config_refs + [ref('opu', 84, 110), ref('opu-seq', 136, 145), ref('fir-opu-ports', 1, 8), ref('hardfloat-round', 235, 288), ref('hardfloat-convert', 58, 86), ref('hardfloat-fma', 264, 292)],
            input_type_pairs=[[a, b] for a in fp8 for b in fp8], notes=['Separate A/B formats; exact input expansion, then sequential FP32 FMA using frm and tininess-after-rounding. OPU exceptionFlags are not connected to architectural fflags. No FPGA/RTL bit-exact certification yet.'])
        row(hart, 'tile-row-transport', 'vme', ['i32', 'u32', 'f32'], ['i32', 'u32', 'f32'], ['tile_row_read', 'tile_row_write', 'tile_zero'], status=mx_status, widths=[32], refs=[ref('early-decode', 43, 55), ref('opu', 195, 207), ref('backend', 441, 450)], notes=['Raw 32-bit transport, not a conversion or FP32 matrix multiply.'])
        row(hart, 'tile-column-write', 'vme', ['i32', 'u32', 'f32'], ['i32', 'u32', 'f32'], ['tile_column_write'], status=mx_status, widths=[32], refs=[ref('opu', 195, 199), ref('opu-seq', 303, 308)])
        row(hart, 'tile-column-read', 'vme', ['i32', 'u32', 'f32'], ['i32', 'u32', 'f32'], ['tile_column_read'], status='not_configured', widths=[32], refs=[ref('saturn-params', 371, 373), ref('shuttle-vec', 24, 28), ref('opu', 209, 215), ref('backend', 441, 450), ref('fir-opu-ports', 1, 8)], notes=['No column readout ports in elaborated OPU. The instruction may decode but cannot be certified as a column read. Do not invent an illegal-instruction trap for this missing datapath.'])
        row(hart, 'other-native-matmul', 'vme', ['i4', 'u4', 'i16', 'u16', 'i32', 'u32', 'i64', 'u64', 'f16', 'bf16', 'f32', 'f64'], [], ['mac'], status='not_configured', refs=[ref('saturn-params', 397, 406), ref('early-decode', 43, 55), ref('opu', 19, 24)], notes=['VME computes 8-bit operands into 32-bit tiles; 32-bit tile moves do not make other input types native matrix operations.'])

    data = {'schema_version': 1, 'scope': 'hardware-source-audit', 'bitstream_match_verified': False,
            'model_support_is_separate': True, 'hardware_manifest_sha256': digest((directory / 'manifest.json').read_bytes()),
            'repositories': repositories, 'sources': sources,
            'scalar_bf16_decoder_proof': scalar_bf16_decoder_proof((directory / sources['scalar-instructions']['snapshot']).read_text(), (directory / sources['custom-instructions']['snapshot']).read_text()),
            'types': {name: {'category': 'integer' if name[0] in ('i', 'u') else 'floating'} for name in ['i4', 'u4'] + ints + fp + ['bf16'] + fp8},
            'aliases': {'fp8': 'ambiguous: choose ofp8_e4m3 or ofp8_e5m2 explicitly', 'bf8': 'no separately identified BF8 type; do not silently alias this name'},
            'capabilities': rows,
            'formats': {
                'ofp8_e4m3': {'bits': 8, 'exponent_bits': 4, 'fraction_bits': 3, 'max_finite': 448, 'min_positive_subnormal_power_of_two': -9, 'infinity': False, 'nan_bit_patterns': ['0x7f', '0xff'], 'signed_zero': True, 'evidence': [ref('fp8-expand', 8, 29)]},
                'ofp8_e5m2': {'bits': 8, 'exponent_bits': 5, 'fraction_bits': 2, 'max_finite': 57344, 'min_positive_subnormal_power_of_two': -16, 'infinity': True, 'signed_zero': True, 'evidence': [ref('mx-types', 6, 10), ref('fp8-expand', 8, 10)]},
            },
            'discrepancies': [
                {'id': 'dma-comment-vs-units', 'description': 'dmaParams comment says memcpy only, but actual Unified execution unit factories instantiate integer and shared-scalar FP arithmetic; zero-depth queue is bypass.', 'evidence': [ref('saturn-params', 97, 110), ref('saturn-params', 203, 216), ref('issue-queue', 20, 46)]},
                {'id': 'scalar-zfbfmin-advertisement', 'description': 'Compute DTS advertises Zfbfmin, but neither scalar BF16 conversion encoding intersects any of the 835 normal/custom scalar instruction definitions. The source decoder has no execution entry; image association and RTL execution certification remain separate.', 'evidence': [ref('dts', 36, 36), ref('scalar-instructions', 12, 818), ref('custom-instructions', 8, 38), ref('fpu', 64, 173), ref('shuttle-exec', 243, 263), ref('early-decode', 36, 70)]},
                {'id': 'column-readout-absent', 'description': 'Column-read opcode can decode while useOpuColReadout=false; elaborated OPU has no out_col. Reference Spike column-read tests do not certify this hardware behavior.', 'evidence': [ref('saturn-params', 371, 373), ref('backend', 441, 450), ref('fir-opu-ports', 1, 8)]},
                {'id': 'vector-minifloat-operation-subsets', 'description': 'Mx FMA and conversions support additional formats, but compare/divide/conversion-to-integer do not thereby gain matching minifloat semantics.', 'evidence': [ref('fp-comp', 41, 50), ref('fp-div', 230, 238), ref('fp-conv', 84, 95)]},
            ],
            'limits': ['Configured source paths are not an execution certification or deployed bitstream identity.', 'No cycle latency, throughput, utilization peak, or accuracy parameter is inferred from this matrix.', 'Not-configured dtype semantics do not necessarily imply the RTL traps on every corresponding broad decode.']}
    verify(data, directory)
    (directory / 'dtypes.json').write_text(json.dumps(data, indent=2) + '\n')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--output', type=Path, default=HERE)
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--verify-live', action='store_true')
    args = parser.parse_args()
    data = json.loads((args.output / 'dtypes.json').read_text()) if args.verify or args.verify_live else generate(args.root, args.output)
    print(json.dumps(verify(data, args.output, args.root if args.verify_live else None), indent=2))


if __name__ == '__main__':
    main()
