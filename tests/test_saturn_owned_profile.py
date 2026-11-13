"""Physical ownership remains attached to its command across later acceptance."""
import copy
import unittest

from iris_model.saturn_owned_profile import profile


class Instructions:
    def read(self,pc):
        return {0x1000:0x57,0x1010:0x80057}[pc]


def command(sequence=0):
    return {'reset_epoch':1,'sequence':sequence,'EX_edge':sequence,
        'pc':0x1000+16*sequence,'instruction':0x57+0x80000*sequence,
        'EX_fired':True,'pc_known':True,'caller_node':9-sequence}


def event(kind,edge,sequence=0,**extra):
    row={'kind':kind,'source':'exact.source.signal','hart':0,'source_edge':edge,
        'tb':2*edge+3,'amount':0,'command':command(sequence)}
    row.update(extra);return row


def fixture():
    rows=[event('frontend_issue_accept',1),
        event('MRF_INT8_commit',2,amount=1,bit_mask=[0xffffffff],data_words=[0x87654321]),
        event('frontend_issue_accept',3,1),
        event('MRF_INT8_commit',4,amount=1,bit_mask=[0xffffffff],data_words=[0x76543210]),
        event('TL_transaction_accept',5,1,transaction=7,address=0x80000000,bytes=16,transport_source=2,memory_tag=3),
        event('TL_transaction_complete',9,1,transaction=7,address=0x80000000,bytes=16,transport_source=2,memory_tag=3)]
    counts={0:{'frontend_issue_accept':2,'MRF_INT8_commit':2,'TL_transaction_accept':1,'TL_transaction_complete':1},1:{},2:{}}
    return rows,counts


def run(rows,counts):
    return profile(rows,Instructions(),[(0x1000,0x1004,'original'),(0x1010,0x1014,'later')],1e9,counts)


class OwnedSourceTests(unittest.TestCase):
    def test_late_write_keeps_original_elf_owner_without_neighbor_or_node_heuristics(self):
        rows,counts=fixture();summary,timeline=run(rows,counts)
        functions={f['function']:f for f in summary['functions']}
        self.assertEqual(functions['original']['kind_counts']['MRF_INT8_commit'],2)
        self.assertNotIn('MRF_INT8_commit',functions['later']['kind_counts'])
        self.assertEqual(functions['original']['write_enable_bits_by_kind']['MRF_INT8_commit'],64)
        self.assertEqual(functions['later']['accepted_commands'],1)
        self.assertIsNone(summary['retired_instructions']);self.assertIsNone(summary['occupancy'])
        points=[p for p in timeline['traceEvents']if p['ph']=='i']
        self.assertTrue(all('dur'not in p for p in points))
        write=next(p for p in points if p['args']['tb']==11)
        self.assertEqual(write['args']['function'],'original')
        self.assertNotIn('numeric_values',summary)

    def test_source_request_response_lifetime_is_separate_from_dram_or_contention(self):
        summary,timeline=run(*fixture());span=summary['transport_transactions'][0]
        self.assertEqual((span['elapsed_TB_ticks'],span['elapsed_source_edges'],span['declared_transaction_bytes']),(8,4,16))
        self.assertEqual(summary['pending_transport_transactions'],0)
        function=next(f for f in summary['functions']if f['function']=='later')
        self.assertEqual(dict(function['declared_bytes_by_kind']),{'TL_transaction_accept':16,'TL_transaction_complete':16})
        self.assertIsNone(summary['stall_breakdown']);self.assertIsNone(summary['roofline'])
        self.assertEqual(next(p for p in timeline['traceEvents']if p['ph']=='X')['dur'],0.008)

    def test_source_generation_cannot_change_pc_raw_instruction_or_caller(self):
        for field,value in [('pc',0x1010),('instruction',0x80057),('caller_node',777),('EX_edge',2)]:
            rows,counts=fixture();rows[3]['command'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):run(rows,counts)

    def test_physical_work_needs_accepted_generation_and_complete_counts(self):
        rows,counts=fixture()
        with self.assertRaisesRegex(ValueError,'accepted'):run(rows[1:],counts)
        with self.assertRaisesRegex(ValueError,'counts'):run(rows[:-1],counts)
        rows,counts=fixture();rows.insert(1,copy.deepcopy(rows[0]))
        with self.assertRaisesRegex(ValueError,'Duplicate'):run(rows,counts)

    def test_source_response_cannot_change_owner_or_packet_payload(self):
        for field,value in [('transaction',8),('transport_source',3),('memory_tag',4),('bytes',32),('address',0x80000010)]:
            rows,counts=fixture();rows[-1][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):run(rows,counts)

    def test_unowned_scrub_never_attributed_to_elf_symbol_zero(self):
        row=event('VRF_scrub_commit',0,amount=32,bit_mask=[0xffffffff],data_words=[0]);del row['command']
        counts={0:{'VRF_scrub_commit':1},1:{},2:{}}
        summary,_=profile([row],Instructions(),[(0,16,'wrong')],1e9,counts)
        self.assertIsNone(summary['functions'][0]['function'])
        self.assertEqual(summary['functions'][0]['accepted_commands'],0)
        self.assertIsNone(summary['retired_instructions'])

    def test_types_clock_and_order_refuse(self):
        for field,value in [('hart',True),('tb',-1),('source_edge',True),('amount',2**64),('source','')]:
            rows,counts=fixture();rows[0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):run(rows,counts)
        rows,counts=fixture();rows[2],rows[3]=rows[3],rows[2]
        with self.assertRaises(ValueError):run(rows,counts)
        with self.assertRaises(ValueError):profile([],Instructions(),[],0,{0:{},1:{},2:{}})


if __name__=='__main__':unittest.main()
