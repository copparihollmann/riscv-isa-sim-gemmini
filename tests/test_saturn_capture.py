import copy
import gzip
import hashlib
import io
from pathlib import Path
import struct
import tempfile
import unittest

from iris_model.saturn_capture import MAGIC, Reader, layout_from_documents, verified_capture


def documents():
    physical, profiles = {}, {}
    for kind, harts in [('compute', [0, 1]), ('rocket', [2])]:
        physical[kind] = {'source_harts': harts, 'clock_IDs': {str(h): 'source.clock.'+str(h) for h in harts},
            'words': {'input': [
                {'name': 'reset', 'width': 1, 'lo': 0, 'word_width': 1, 'word_index': 0, 'direction': 'input'},
                {'name': 'wide', 'width': 72, 'lo': 0, 'word_width': 64, 'word_index': 1, 'direction': 'input'},
                {'name': 'wide', 'width': 72, 'lo': 64, 'word_width': 8, 'word_index': 2, 'direction': 'input'}],
                'output': [{'name': 'busy', 'width': 1, 'lo': 0, 'word_width': 1, 'word_index': 0, 'direction': 'output'}]}}
        profiles[kind] = {'unresolved': [], 'word_count': 2, 'fields': [
            {'name': 'dis.token', 'width': 16, 'words': [{'lo': 0, 'width': 16, 'index': 0}]},
            {'name': 'raw.unreset_payload', 'width': 64, 'words': [{'lo': 0, 'width': 64, 'index': 1}]}]}
    return physical, {'schema': 'iris.saturn_typed_internal_activity.v1', 'profiles': profiles}


def capture(records=None, magic=MAGIC, counts=(6, 6, 6)):
    if records is None: records = [(3, 0, 0), (3, 0, 1), (3, 0, 2), (5, 1, 0), (5, 1, 2), (7, 1, 1)]
    data = bytearray(struct.pack('<4Q', magic, *counts))
    payload = (1, 0x123456789ABCDEF0, 0xAB, 0, 7, 0xDEADBEEF)
    for tb, edge, hart in records:
        data += struct.pack('<4Q', tb, edge, hart, 6) + struct.pack('<6Q', *payload)
    return bytes(data)


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.physical, self.activity = documents()
        self.layout = layout_from_documents(self.physical, self.activity)

    def read(self, raw):
        reader = Reader(io.BytesIO(raw), self.layout)
        return list(reader), reader

    def test_three_clocks_and_wide_fields_preserve_raw_bits_without_time_inference(self):
        frames, reader = self.read(capture())
        self.assertTrue(reader.finished); self.assertEqual(reader.counts, [2, 2, 2])
        first = frames[0]
        self.assertEqual(first.raw_value('input.wide'), 0xAB123456789ABCDEF0)
        self.assertEqual(first.raw_value('input.reset'), 1)
        self.assertEqual(first.raw_value('dis.token'), 7)
        self.assertEqual(first.raw_value('raw.unreset_payload'), 0xDEADBEEF)
        self.assertFalse(hasattr(first, 'known_mask'))
        self.assertFalse(hasattr(first, 'mcycle'))
        self.assertEqual((frames[-1].hart, frames[-1].tb, frames[-1].source_edge, frames[-1].source_clock_id),
                         (1, 7, 1, 'source.clock.1'))

    def test_changed_magic_or_excessive_profile_count_is_rejected_before_payload(self):
        for raw in [capture(magic=0), capture(counts=(2**63, 6, 6))]:
            with self.subTest(raw=raw[:32]), self.assertRaisesRegex(ValueError, 'magic/profile'):
                self.read(raw)

    def test_missing_duplicate_or_nonzero_initial_edge_refuses(self):
        for records in [[(3,1,0)], [(3,0,0),(5,2,0)], [(3,0,0),(5,0,0)]]:
            with self.subTest(records=records), self.assertRaisesRegex(ValueError, 'source edge'):
                self.read(capture(records))

    def test_global_and_per_hart_clock_regressions_refuse(self):
        for records in [[(5,0,0),(3,0,1)], [(3,0,0),(3,1,0)]]:
            with self.subTest(records=records), self.assertRaisesRegex(ValueError, 'clock order'):
                self.read(capture(records))

    def test_invalid_hart_or_per_record_word_count_refuses(self):
        raw = bytearray(capture()); struct.pack_into('<Q',raw,32+16,3)
        with self.assertRaisesRegex(ValueError,'hart/word count'): self.read(bytes(raw))
        raw = bytearray(capture()); struct.pack_into('<Q',raw,32+24,7)
        with self.assertRaisesRegex(ValueError,'hart/word count'): self.read(bytes(raw))

    def test_truncated_header_or_payload_and_missing_hart_refuse(self):
        for raw in [b'', capture()[:31], capture()[:60], capture()[:-1]]:
            with self.subTest(size=len(raw)), self.assertRaisesRegex(ValueError,'Truncated'):
                self.read(raw)
        with self.assertRaisesRegex(ValueError,'missing a configured hart'):
            self.read(capture([(3,0,0),(3,0,1)]))

    def test_padding_bits_are_checked_only_when_raw_field_is_read(self):
        raw = bytearray(capture()); struct.pack_into('<Q',raw,64+2*8,0x100)
        frames, _ = self.read(bytes(raw))
        with self.assertRaisesRegex(ValueError,'Out-of-width'): frames[0].raw_value('input.wide')
        self.assertEqual(frames[0].raw_value('dis.token'),7)
        with self.assertRaisesRegex(ValueError,'Unknown telemetry'): frames[0].raw_value('missing')

    def test_schema_missing_overlapping_or_mislabelled_fields_refuse(self):
        variants = []
        p,a = documents();a['profiles']['compute']['fields'][1]['words'][0]['index']=0;variants.append((p,a))
        p,a = documents();a['profiles']['compute']['word_count']=3;variants.append((p,a))
        p,a = documents();a['profiles']['compute']['unresolved']=['unknown'];variants.append((p,a))
        p,a = documents();p['compute']['words']['input'][2]['lo']=0;variants.append((p,a))
        p,a = documents();p['compute']['words']['input'][1]['word_index']=True;variants.append((p,a))
        p,a = documents();p['compute']['source_harts']=[0,True];variants.append((p,a))
        p,a = documents();p['rocket']['clock_IDs'].clear();variants.append((p,a))
        for p,a in variants:
            with self.subTest(physical=p), self.assertRaises(ValueError): layout_from_documents(p,a)

    def test_layout_is_immutable_and_reader_single_use(self):
        with self.assertRaises(TypeError): self.layout.profiles['compute']=None
        with self.assertRaises(TypeError): self.layout.profiles['compute'].fields['new']=None
        _,reader=self.read(capture())
        with self.assertRaisesRegex(ValueError,'single-use'): list(reader)


class VerifiedFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.path = self.root/'activity.gz'
        self.path.write_bytes(gzip.compress(capture(),mtime=0))
        self.digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.layout = layout_from_documents(*documents())

    def test_verified_file_requires_exact_hash_and_complete_consumption(self):
        with verified_capture(self.path,self.layout,self.digest) as reader: self.assertEqual(len(list(reader)),6)
        with self.assertRaisesRegex(ValueError,'SHA256'):
            with verified_capture(self.path,self.layout,'0'*64) as reader: list(reader)
        with self.assertRaisesRegex(ValueError,'Complete capture consumption'):
            with verified_capture(self.path,self.layout,self.digest) as reader: next(iter(reader))

    def test_changed_source_and_symlink_refuse(self):
        with self.assertRaisesRegex(ValueError,'changed while reading'):
            with verified_capture(self.path,self.layout,self.digest) as reader:
                list(reader)
                with self.path.open('ab') as stream: stream.write(b'changed')
        alias=self.root/'alias.gz';alias.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError,'ordinary file'):
            with verified_capture(alias,self.layout,self.digest): pass

    def test_unfrozen_or_truncated_file_refuses(self):
        with self.assertRaisesRegex(ValueError,'Frozen capture SHA256'):
            with verified_capture(self.path,self.layout,None): pass
        self.path.write_bytes(gzip.compress(capture()[:-1],mtime=0));digest=hashlib.sha256(self.path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'Truncated'):
            with verified_capture(self.path,self.layout,digest) as reader:list(reader)


if __name__ == '__main__': unittest.main()
