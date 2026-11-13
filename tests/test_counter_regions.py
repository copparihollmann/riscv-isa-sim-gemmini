import copy
import json
import unittest

from iris_model.counter_regions import annotate, observations, region_metrics
from iris_model.guest_regions import annotate as join_regions, fixture_clocks
from iris_model.report import profile


def raw(csr=0xB00, rd=5):
    return csr << 20 | 2 << 12 | rd << 7 | 0x73


class Image:
    def __init__(self, code):self.code=code
    def read(self,pc):return self.code.get(pc,0x13)


class CapturedCounterRegionTests(unittest.TestCase):
    def setUp(self):
        def event(i,hart,pc,submitted,start,end,resource,**extra):
            return dict(id=i,hart=hart,pc=pc,submitted=submitted,start=start,end=end,resource=resource,
                        name='synthetic operation',completed=True,lane=0,bytes=0,macs=0,deps=[],region='',**extra)
        events=[event(0,0,0,0,2,4,'csr0'),event(1,0,4,0,0,8,'vme'),
                event(2,0,8,3,10,16,'memory'),event(3,0,12,10,12,14,'csr0'),
                event(4,1,16,1,1,9,'memory'),event(5,1,20,0,1,3,'csr1'),
                event(6,1,24,14,15,17,'csr1'),event(7,0,28,5,17,19,'queue')]
        events[1]['macs']=64;events[2]['bytes']=64;events[4]['bytes']=32
        self.image=Image({0:raw(),12:raw(),20:raw(0xC00,6),24:raw(0xC00,6)})
        def read(hart,seq,node,value,cycle,csr=0xB00,rd=5):
            return dict(hart=hart,sequence=seq,node=node,pc=events[node]['pc'],raw=raw(csr,rd),csr=csr,
                        destination=rd,result_discarded=rd==0,value=value,read_cycle=cycle,read_phase='synthetic pre-completion read')
        self.graph={'schema_version':1,'harts':2,'cycles':20,'status':'experimental_uncalibrated',
                    'timing_mode':'uncalibrated-integration-fixture','base_clock_hz':100,'clock_source':'synthetic fixture',
                    'hart_cycle_dividers':[1,2],'resources':{'csr0':1,'csr1':1,'vme':1,'memory':1,'queue':1},
                    'events':events,'traffic_accounting':'instrumented','arithmetic_accounting':'instrumented',
                    'counter_read_observations':{'schema_version':1,'complete':True,'source':'synthetic captured-CSR fixture, not RTL evidence',
                        'reads':[read(0,0,0,100,2),read(0,1,3,107,12),read(1,0,5,7,1,0xC00,6),read(1,1,6,14,15,0xC00,6)]}}

    def console(self,hart=0,start=100,end=107,name='kernel'):
        return 'IRIS_REGION '+json.dumps(dict(case_id=name,region='compute',hart=hart,start_cycle=start,end_cycle=end))+'\n'

    def test_actual_read_timestamp_replaces_fixed_offset_and_completion_time(self):
        joined=join_regions(self.graph,self.console(),self.image,{0:1,1:2})
        boundary=joined['region_boundaries'][0]
        self.assertEqual((boundary['start'],boundary['end'],boundary['guest_mcycle_delta']),(2,12,7))
        self.assertEqual(joined['events'],self.graph['events'])
        old=copy.deepcopy(self.graph);old.pop('counter_read_observations')
        with self.assertRaisesRegex(ValueError,'missing or ambiguous'):join_regions(old,self.console(),self.image,{0:1,1:2})

    def test_crossing_events_keep_dependency_spans_and_intersect_occupancy(self):
        joined=annotate(self.graph,self.console()+self.console(1,7,14),self.image)
        summary,timeline=profile(joined,100,'synthetic fixture',[(4,8,'matmul')],
                                 {'vme':{'source':'synthetic test peak','macs_per_cycle':8}})
        h0,h1=summary['observed_regions']
        self.assertEqual((h0['cycles'],h0['guest_mcycle_delta']),(10,7))
        self.assertEqual((h0['units']['vme']['busy_cycles'],h0['units']['vme']['completed_macs']),(6,64))
        self.assertEqual(h0['units']['vme']['achieved_fraction_of_peak'],0.8)
        self.assertEqual((h0['units']['memory']['busy_cycles'],h0['units']['memory']['operation_wait_cycles_sum']),(2,7))
        self.assertEqual(h0['units']['memory']['completed_bytes'],0)
        self.assertEqual((h0['units']['queue']['busy_cycles'],h0['units']['queue']['operation_wait_cycles_sum']),(0,7))
        self.assertEqual((h1['units']['memory']['busy_cycles'],h1['units']['memory']['completed_bytes']),(8,32))
        self.assertEqual(next(f for f in h0['functions'] if f['function']=='matmul')['active_cycles'],6)
        self.assertIsNone(h0['roofline']);self.assertIsNone(h0['stall_breakdown'])
        self.assertEqual(sum(t['cat']=='captured counter read' for t in timeline['traceEvents']),4)
        self.assertEqual(sum(t['cat']=='guest region' for t in timeline['traceEvents']),2)
        load=next(t for t in timeline['traceEvents'] if t['ph']=='X' and t.get('args',{}).get('node')==2)
        self.assertEqual(load['dur'],6*1e6/100)

    def test_counter_wrap_or_software_write_does_not_redefine_elapsed_time(self):
        graph=copy.deepcopy(self.graph);reads=graph['counter_read_observations']['reads']
        reads[0]['value']=(1<<64)-5;reads[1]['value']=3
        joined=annotate(graph,self.console(start=(1<<64)-5,end=3),self.image)
        result=region_metrics(joined)[0]
        self.assertEqual((result['cycles'],result['guest_mcycle_delta']),(10,8))

    def test_missing_partial_forged_or_misaligned_observations_are_refused(self):
        mutations=[lambda g:g['counter_read_observations'].update(complete=False),
                   lambda g:g['counter_read_observations'].update(schema_version=True),
                   lambda g:g['counter_read_observations']['reads'][0].update(raw=raw(0xB02),csr=0xB02),
                   lambda g:g['counter_read_observations']['reads'][0].update(destination=6),
                   lambda g:g['counter_read_observations']['reads'][0].update(result_discarded=True),
                   lambda g:g['counter_read_observations']['reads'][1].update(sequence=2),
                   lambda g:g['counter_read_observations']['reads'][1].update(read_cycle=1),
                   lambda g:g['counter_read_observations']['reads'][0].update(read_cycle=5),
                   lambda g:g['counter_read_observations']['reads'][0].update(node=99),
                   lambda g:g['events'][0].update(completed=False),
                   lambda g:g['counter_read_observations']['reads'][0].update(value=True)]
        for mutation in mutations:
            graph=copy.deepcopy(self.graph);mutation(graph)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):annotate(graph,self.console(),self.image)

    def add_third_read(self,graph,rd):
        graph['events'].append(dict(graph['events'][3],id=8,pc=32,submitted=15,start=16,end=18))
        graph['counter_read_observations']['reads'].append(dict(graph['counter_read_observations']['reads'][0],
            sequence=2,node=8,pc=32,raw=raw(rd=rd),destination=rd,result_discarded=rd==0,read_cycle=16))
        return Image(dict(self.image.code,**{}))

    def test_duplicate_values_are_ambiguous_but_discarded_results_are_not_anchors(self):
        graph=copy.deepcopy(self.graph);self.add_third_read(graph,5);image=Image(dict(self.image.code));image.code[32]=raw()
        with self.assertRaisesRegex(ValueError,'ambiguous'):annotate(graph,self.console(),image)
        graph=copy.deepcopy(self.graph);self.add_third_read(graph,0);image.code[32]=raw(rd=0)
        self.assertEqual(len(annotate(graph,self.console(),image)['region_boundaries']),1)

    def test_incomplete_and_boundary_tied_payloads_are_not_fabricated(self):
        graph=copy.deepcopy(self.graph);graph.update(partial=True,pending_operations=1)
        graph['events'].append(dict(graph['events'][1],id=8,submitted=10,start=11,end=20,completed=False,macs=999))
        result=profile(annotate(graph,self.console(),self.image),100,'synthetic fixture')[0]['observed_regions'][0]
        self.assertEqual(result['units']['vme']['completed_macs'],64)
        self.assertEqual(result['units']['vme']['incomplete_operations'],1)
        graph['events'][8].update(completed=True,end=12)
        result=profile(annotate(graph,self.console(),self.image),100,'synthetic fixture')[0]['observed_regions'][0]
        self.assertIsNone(result['units']['vme']['completed_macs'])
        self.assertTrue(result['units']['vme']['boundary_mac_completion_unresolved'])

    def test_unknown_traffic_and_arithmetic_stay_unavailable(self):
        graph=copy.deepcopy(self.graph);graph.pop('traffic_accounting');graph['arithmetic_accounting']='not_instrumented'
        result=region_metrics(annotate(graph,self.console(),self.image))[0]
        self.assertIsNone(result['units']['vme']['completed_macs']);self.assertIsNone(result['units']['memory']['completed_bytes'])

    def test_captured_reads_allow_wfi_stopped_clock_without_a_constant_mapping(self):
        text='purpose uncalibrated-integration-fixture\nbase_hz 100\nhart 0 1 0\nhart 1 2 1\n'
        with self.assertRaisesRegex(ValueError,'WFI'):fixture_clocks(text,self.graph)
        self.assertEqual(fixture_clocks(text,self.graph,constant_counter_proof=False),{0:1,1:2})

    def source_fixture(self):
        graph=copy.deepcopy(self.graph)
        graph['source_counter_clock']={'policy':'CSRFile-ungated-pre-edge-stall','source':'independent synthetic source-clock admission fixture'}
        text='purpose uncalibrated-integration-fixture\nbase_hz 100\nhart 0 1 source\nhart 1 2 source\ncounter_policy source-ungated-stall\n'
        return graph,text

    def test_source_idle_enum_uses_captured_values_and_read_timestamps(self):
        graph,text=self.source_fixture()
        clocks=fixture_clocks(text,graph,constant_counter_proof=False)
        self.assertEqual(clocks,{0:1,1:2})
        joined=join_regions(graph,self.console(),self.image,clocks)
        region=region_metrics(joined)[0]
        self.assertEqual((region['cycles'],region['guest_mcycle_delta']),(10,7))
        self.assertEqual(joined['region_projection_method'],'captured_counter_reads')

    def test_source_policy_never_falls_back_after_capture_is_removed(self):
        graph,text=self.source_fixture();clocks=fixture_clocks(text,graph,constant_counter_proof=False)
        graph.pop('counter_read_observations')
        with self.assertRaisesRegex(ValueError,'fallback is forbidden'):
            join_regions(graph,self.console(),self.image,clocks)
        with self.assertRaises(ValueError):fixture_clocks(text,graph,constant_counter_proof=False)

    def test_source_policy_cannot_claim_constant_mapping_or_mix_numeric_idle(self):
        graph,text=self.source_fixture()
        for fixture in (text,text.replace('0 1 source','0 1 0'),text.replace('1 2 source','1 2 1')):
            with self.subTest(fixture=fixture),self.assertRaises(ValueError):fixture_clocks(fixture,graph)
        for fixture in (text.replace('0 1 source','0 1 0'),text.replace('1 2 source','1 2 1')):
            with self.subTest(fixture=fixture),self.assertRaises(ValueError):fixture_clocks(fixture,graph,constant_counter_proof=False)

    def test_source_policy_requires_matching_graph_declaration_and_complete_capture(self):
        graph,text=self.source_fixture()
        for change in (lambda g:g.pop('source_counter_clock'),
                       lambda g:g.update(source_counter_clock=None),
                       lambda g:g['source_counter_clock'].update(policy='assumed'),
                       lambda g:g['source_counter_clock'].update(source=''),
                       lambda g:g['counter_read_observations'].update(complete=False)):
            bad=copy.deepcopy(graph);change(bad)
            with self.subTest(change=change),self.assertRaises(ValueError):fixture_clocks(text,bad,constant_counter_proof=False)
        for bad in (text.replace('counter_policy source-ungated-stall',''),
                    text+'counter_policy source-ungated-stall\n',text.replace('source-ungated-stall','unknown')):
            with self.subTest(fixture=bad),self.assertRaises(ValueError):fixture_clocks(bad,graph,constant_counter_proof=False)

    def test_nested_regions_share_intersections_without_mutating_global_history(self):
        graph=copy.deepcopy(self.graph)
        extras=[]
        for i,(pc,cycle,value) in enumerate([(32,5,101),(36,10,106)]):
            node=8+i;graph['events'].append(dict(graph['events'][0],id=node,pc=pc,submitted=cycle-1,start=cycle,end=cycle+1))
            extras.append(dict(graph['counter_read_observations']['reads'][0],node=node,pc=pc,read_cycle=cycle,value=value,sequence=i+1))
        original=graph['counter_read_observations']['reads'];original[1]['sequence']=3
        graph['counter_read_observations']['reads']=[original[0],*extras,original[1],*original[2:]]
        image=Image(dict(self.image.code));image.code.update({32:raw(),36:raw()})
        joined=annotate(graph,self.console(name='outer')+self.console(start=101,end=106,name='inner'),image)
        metrics=profile(joined,100,'synthetic fixture')[0]['observed_regions']
        self.assertEqual([r['units']['vme']['busy_cycles'] for r in metrics],[6,3])
        self.assertEqual(joined['events'],graph['events'])


if __name__=='__main__':unittest.main()
