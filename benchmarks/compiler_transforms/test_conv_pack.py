"""Independent host admission of the exact C panel-packing candidate.

Checks asymmetric padding, layouts, stride, batch boundaries, row tails,
workspace redzones and assembled I32 results against a direct convolution.
No FPGA or simulator is invoked.
"""
import ctypes as C
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import numpy as np

HERE = Path(__file__).resolve().parent


class Shape(C.Structure):
    _fields_ = [(x, C.c_size_t) for x in
                ('batch', 'ci', 'co', 'h', 'w', 'kh', 'kw', 'stride', 'pt', 'pl', 'oh', 'ow')]
    _fields_ += [('nhwc', C.c_uint), ('hwio', C.c_uint)]


class ConvPackingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = shutil.which('cc')
        if cc is None:
            raise unittest.SkipTest('a host C compiler is required')
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        src = root / 'wrapper.c'
        src.write_text('''#include "conv_pack.h"
void pa(const struct iris_conv_shape*s,const int8_t*a,int8_t*p,size_t f,size_t n){iris_conv_pack_a(s,a,p,f,n);}
void pb(const struct iris_conv_shape*s,const int8_t*b,int8_t*p){iris_conv_pack_b(s,b,p);}
int direct(const struct iris_conv_shape*s){return iris_conv_direct_a(s);}
''')
        subprocess.run([cc, '-O2', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        '-I', str(HERE), str(src), '-o', str(root / 'pack.so')], check=True)
        cls.lib = C.CDLL(str(root / 'pack.so'))
        cls.lib.pa.argtypes = [C.POINTER(Shape), C.c_void_p, C.c_void_p, C.c_size_t, C.c_size_t]
        cls.lib.pb.argtypes = [C.POINTER(Shape), C.c_void_p, C.c_void_p]
        cls.lib.direct.argtypes = [C.POINTER(Shape)]
        cls.lib.direct.restype = C.c_int

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def check_geometry(self, geom):
        batch, ci, co, h, w, kh, kw, stride, pads = geom
        pt, pb, pl, pr = pads
        oh = (h + pt + pb - kh) // stride + 1
        ow = (w + pl + pr - kw) // stride + 1
        rng = np.random.default_rng(1931 + h + ci)
        src = rng.integers(-128, 128, (batch, ci, h, w), dtype=np.int16).astype(np.int8)
        weights = rng.integers(-128, 128, (co, ci, kh, kw), dtype=np.int16).astype(np.int8)
        padded = np.pad(src, ((0, 0), (0, 0), (pt, pb), (pl, pr)))
        # Independent direct convolution order, not the C panel-index formula.
        expected = np.zeros((batch, oh, ow, co), dtype=np.int64)
        for y in range(oh):
            for x in range(ow):
                patch = padded[:, :, y*stride:y*stride+kh, x*stride:x*stride+kw].astype(np.int64)
                for oc in range(co):
                    expected[:, y, x, oc] = (patch * weights[oc].astype(np.int64)).sum((1, 2, 3))
        rows, reduction = batch * oh * ow, ci * kh * kw
        expected = expected.reshape(rows, co).astype(np.int32)
        for nhwc in (0, 1):
            for hwio in (0, 1):
                a = np.ascontiguousarray(src.transpose(0, 2, 3, 1) if nhwc else src)
                b = np.ascontiguousarray(weights.transpose(2, 3, 1, 0) if hwio else weights)
                shape = Shape(batch, ci, co, h, w, kh, kw, stride, pt, pl, oh, ow, nhwc, hwio)
                bguard = np.full(reduction * co + 32, 0x5a, np.uint8)
                bpacked = bguard[16:-16].view(np.int8).reshape(reduction, co)
                self.lib.pb(C.byref(shape), b.ctypes.data, bpacked.ctypes.data)
                np.testing.assert_array_equal(bpacked, weights.reshape(co, -1).T)
                self.assertTrue((bguard[:16] == 0x5a).all() and (bguard[-16:] == 0x5a).all())
                for tile in (1, 7, 16, 32, 128, rows):
                    out = np.zeros((rows, co), np.int32)
                    for first in range(0, rows, tile):
                        count = min(tile, rows - first)
                        aguard = np.full(reduction * count + 32, 0xa5, np.uint8)
                        apacked = aguard[16:-16].view(np.int8).reshape(reduction, count)
                        self.lib.pa(C.byref(shape), a.ctypes.data, apacked.ctypes.data, first, count)
                        out[first:first+count] = (apacked.T.astype(np.int64) @ bpacked.astype(np.int64)).astype(np.int32)
                        self.assertTrue((aguard[:16] == 0xa5).all() and (aguard[-16:] == 0xa5).all())
                    np.testing.assert_array_equal(out, expected)
                if self.lib.direct(C.byref(shape)):
                    direct = (a.reshape(ci, rows).T.astype(np.int64) @ bpacked.astype(np.int64)).astype(np.int32)
                    np.testing.assert_array_equal(direct, expected)

    def test_nchw_nhwc_oihw_hwio_asymmetric_stride_and_tail(self):
        cases = [(1, 3, 7, 5, 9, 3, 3, 1, (1, 2, 0, 1)),
                 (2, 2, 5, 9, 7, 3, 2, 2, (0, 1, 2, 0)),
                 (1, 4, 8, 7, 5, 1, 1, 1, (0, 0, 0, 0)),
                 (2, 1, 3, 8, 11, 1, 1, 2, (0, 0, 0, 0))]
        for geom in cases:
            with self.subTest(geometry=geom):
                self.check_geometry(geom)

    def test_direct_view_rejects_incompatible_geometries(self):
        good = Shape(1, 3, 4, 5, 7, 1, 1, 1, 0, 0, 5, 7, 0, 0)
        self.assertEqual(self.lib.direct(C.byref(good)), 1)
        for name, value in [('batch', 2), ('nhwc', 1), ('kh', 3), ('kw', 3),
                            ('stride', 2), ('pt', 1), ('pl', 1), ('oh', 4), ('ow', 6)]:
            changed = Shape.from_buffer_copy(good)
            setattr(changed, name, value)
            with self.subTest(field=name):
                self.assertEqual(self.lib.direct(C.byref(changed)), 0)


if __name__ == '__main__':
    unittest.main()
