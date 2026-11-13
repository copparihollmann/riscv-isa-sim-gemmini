"""Admission controls for numeric readback of an intentionally stopped guest."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('cpu_readback', Path(__file__).resolve().parents[1]/'timing/cpu_layout_readback.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Code:
    def read(self, pc):
        return 0xB0002E73


def evidence():
    functions, words, observations = [], [], []
    for f in range(64):
        pc = 0x80001000+f*64
        functions.append(dict(mode='compact' if f < 32 else 'wide', offset=2*(f % 32),
                              loop_pc=pc+4, begin_pc=pc, end_pc=pc+16))
    for index in range(2304):
        h, ni, f = index % 3, index//9 % 4, index//36
        n = (16, 64, 256, 1024)[ni]
        fn = functions[f]
        start, end = index*10000+100, index*10000+100+3*n+10
        words.extend((start, end, 3*n+2+(h == 2), h+1+3*n, n,
                      fn['loop_pc'], fn['begin_pc'], fn['end_pc']))
        for k, (pc, value) in enumerate(((fn['begin_pc'], start), (fn['end_pc'], end))):
            observations.append(dict(hart=h, sequence=(index//3)*2+k, pc=pc, value=value,
                csr=0xB00, result_discarded=False, raw=Code().read(pc), read_cycle=value+1))
    words.extend((0, 0x8000F000, 0x8000F004, 0x8000F008))
    proof = dict(functions=functions, all64_actual_loop_offsets_and_opcode_widths_verified=True)
    return words, proof, observations


class ReadbackTests(unittest.TestCase):
    def setUp(self):
        self.words, self.proof, self.observations = evidence()

    def decode(self, words=None, observations=None):
        text = ':\n'+''.join(f'0x{w:016x}\n' for w in (self.words if words is None else words))
        return MODULE.decode_words(text, self.proof,
            self.observations if observations is None else observations, Code())

    def test_complete_numeric_main_records(self):
        rows = self.decode()
        self.assertEqual(len(rows), 2304)
        self.assertEqual({r['hart'] for r in rows}, {0, 1, 2})

    def test_corrupt_numeric_or_instruction_counter_or_pc_is_rejected(self):
        for field in (2, 3, 4, 5, 6, 7):
            with self.subTest(field=field):
                words = self.words.copy(); words[8*2201+field] += 1
                with self.assertRaises(ValueError): self.decode(words)

    def test_failure_flag_and_incomplete_dump_are_rejected(self):
        words = self.words.copy(); words[-4] = 1
        for wrong in (words, self.words[:-1]):
            with self.assertRaises(ValueError): self.decode(wrong)

    def test_missing_or_ambiguous_actual_counter_observation_is_rejected(self):
        for wrong in (self.observations[1:], self.observations+[self.observations[0]]):
            with self.assertRaises(ValueError): self.decode(observations=wrong)

    def test_discarded_or_wrong_instruction_counter_is_rejected(self):
        for field, value in (('raw', 0xB0002073), ('result_discarded', True), ('csr', 0xB02)):
            wrong = copy.deepcopy(self.observations); wrong[-1][field] = value
            with self.assertRaises(ValueError): self.decode(observations=wrong)

    def test_unexpected_debugger_trap_is_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.decode_words(':\nReceived trap: load access fault\n', self.proof, [], Code())

    def test_only_unterminated_prefix_tail_may_be_excluded_and_is_counted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'features'
            record = json.dumps({'schema': 'iris.empirical.prefix.v1'})
            path.write_text(record+'\n'+record[:15])
            rows, dropped = MODULE.prefix(path)
            self.assertEqual((len(rows), dropped), (1, 15))
            path.write_text(record+'\n{bad}\n'+record+'\n')
            with self.assertRaises(json.JSONDecodeError): MODULE.prefix(path)


if __name__ == '__main__':
    unittest.main()
