"""Cancellation preserves physical occupancy without inventing retired work."""
import copy
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from iris_model.counter_regions import annotate, observations, region_metrics, METHOD
from iris_model.event_lifecycle import validate_events
from iris_model.guest_regions import annotate as legacy_or_captured
from iris_model.memory_profile import memory_summary
from iris_model.report import profile

ROOT=Path(__file__).resolve().parents[1]
CLOCK=100000000
SOURCE='synthetic cancellation contract; not hardware or timing certification'

def event(node=0, hart=0, submitted=0, start=1, end=4, resource='unit', **extra):
    result=dict(id=node,hart=hart,submitted=submitted,start=start,end=end,resource=resource,
                name='operation',region='kernel',pc=4*node,lane=0,bytes=0,macs=0,deps=[])
    result.update(extra);return result

def graph(events, cycles=20, **extra):
    resources={e['resource']:max(x['lane']for x in events if x['resource']==e['resource'])+1 for e in events}
    result=dict(schema_version=1,status='experimental_uncalibrated',harts=3,cycles=cycles,
                resources=resources,events=events,traffic_accounting='instrumented',arithmetic_accounting='instrumented')
    result.update(extra);return result

def cancel(node=0, start=4, tick=9, submitted=0, issued=True, **extra):
    return event(node,submitted=submitted,start=start if issued else tick,end=tick,
                 completed=False,cancelled=True,issued=issued,cancel_cycle=tick,
                 cancel_reason='redirect before retirement',**extra)

def csr_raw():return(0xb00<<20)|(2<<12)|(5<<7)|0x73
class Image:
    def read(self,pc):return csr_raw()if pc in (0,4,40,44)else 0x13

def counter_graph(operations=()):
    events=[event(0,start=2,end=3,resource='csr0'),event(1,submitted=10,start=12,end=13,resource='csr0')]
    events+=list(operations)
    reads=[dict(hart=0,sequence=i,node=i,pc=4*i,raw=csr_raw(),csr=0xb00,destination=5,
        result_discarded=False,value=100+10*i,read_cycle=2+10*i,read_phase='explicit pre-completion counter observation')for i in range(2)]
    return graph(events,counter_read_observations={'schema_version':1,'complete':True,'source':SOURCE,'reads':reads},
                 timing_mode='uncalibrated-integration-fixture')

def console(hart=0,start=100,end=110):
    return'IRIS_REGION '+json.dumps(dict(case_id='case',region='compute',hart=hart,start_cycle=start,end_cycle=end))+'\n'

def observed(g):return profile(annotate(g,console(),Image()),CLOCK,SOURCE)[0]['observed_regions'][0]

class CancellationOccupancyTests(unittest.TestCase):
    def test_pending_cancel_has_no_busy_work_or_duration_trace(self):
        g=graph([cancel(issued=False,tick=9,submitted=2,bytes=64,macs=128)],cycles=12)
        summary,trace=profile(g,CLOCK,SOURCE,[(0,16,'callee')])
        unit=summary['regions'][0]['units']['unit']
        self.assertEqual((unit['busy_cycles'],unit['bytes'],unit['macs'],unit['incomplete_operations']),(0,0,0,0))
        self.assertEqual(summary['resources']['unit']['busy_cycles'],0)
        self.assertEqual(summary['functions'][0]['active_cycles'],0)
        self.assertEqual(summary['regions'][0]['operation_queue_wait_cycles_sum'],7)
        self.assertEqual(summary['lifecycle_accounting']['cancelled_before_issue'],1)
        self.assertFalse(summary['lifecycle_accounting']['model_operations_are_retired_instructions'])
        self.assertEqual(len(trace['traceEvents']),1);instant=trace['traceEvents'][0]
        self.assertEqual((instant['ph'],instant['cat'],instant['args']['consumed_cycles']),('i','cancellation',0))
        self.assertFalse(instant['args']['issued'])

    def test_issued_cancel_clips_busy_but_nonzero_payload_progress_is_unknown(self):
        g=graph([cancel(start=3,tick=8,submitted=1,bytes=64,macs=32)],cycles=12)
        summary,trace=profile(g,CLOCK,SOURCE,peaks={'unit':{'source':SOURCE,'macs_per_cycle':8}})
        unit=summary['regions'][0]['units']['unit']
        self.assertEqual(unit['busy_cycles'],5);self.assertIsNone(unit['bytes']);self.assertIsNone(unit['macs'])
        self.assertIsNone(unit['achieved_fraction_of_peak']);self.assertEqual(unit['cancelled_operations'],1)
        span,instant=trace['traceEvents'];self.assertEqual(span['ph'],'X');self.assertEqual(span['dur'],5*1e6/CLOCK)
        self.assertEqual(instant['ts'],8*1e6/CLOCK);self.assertTrue(span['args']['cancelled'])
        self.assertFalse(span['args']['completed']);self.assertEqual(instant['args']['consumed_cycles'],5)

    def test_issued_cancel_at_acceptance_has_zero_busy_and_unresolved_payload(self):
        summary,trace=profile(graph([cancel(start=5,tick=5,bytes=8,macs=2)]),CLOCK,SOURCE)
        self.assertEqual(summary['resources']['unit']['busy_cycles'],0)
        self.assertIsNone(summary['regions'][0]['units']['unit']['bytes'])
        self.assertEqual([row['ph']for row in trace['traceEvents']],['i'])
        self.assertTrue(trace['traceEvents'][0]['args']['issued'])

    def test_zero_tick_pending_cancel_is_a_valid_final_graph(self):
        summary,trace=profile(graph([cancel(issued=False,tick=0,bytes=64)],cycles=0),CLOCK,SOURCE)
        self.assertEqual(summary['cycles'],0);self.assertEqual(summary['resources']['unit']['busy_fraction'],0)
        self.assertEqual(summary['regions'][0]['units']['unit']['bytes'],0)
        self.assertEqual(trace['traceEvents'][0]['ts'],0)

    def test_completed_squashed_work_retains_physical_occupancy_and_work(self):
        summary,trace=profile(graph([event(start=3,end=8,completed=True,squashed=True,bytes=16,macs=32)]),CLOCK,SOURCE)
        unit=summary['regions'][0]['units']['unit']
        self.assertEqual((unit['busy_cycles'],unit['bytes'],unit['macs']),(5,16,32))
        self.assertEqual(unit['squashed_completed_model_operations'],1)
        self.assertEqual(summary['functions'][0]['completed_model_operations'],1)
        self.assertTrue(trace['traceEvents'][0]['args']['squashed'])
        self.assertFalse(summary['lifecycle_accounting']['model_operations_are_retired_instructions'])

    def test_partial_snapshot_remains_distinct_from_final_cancellation(self):
        events=[event(0,start=1,end=10,completed=False),cancel(1,issued=False,tick=4,submitted=2)]
        events[1]['deps']=[0]
        summary,trace=profile(graph(events,cycles=10,partial=True,pending_operations=1),CLOCK,SOURCE)
        self.assertEqual(summary['regions'][0]['units']['unit']['incomplete_operations'],1)
        self.assertEqual(summary['lifecycle_accounting']['cancelled_before_issue'],1)
        self.assertFalse(any(t['cat']=='dependency'for t in trace['traceEvents']))

    def test_union_busy_matches_independent_tick_set_across_three_harts(self):
        randomizer=random.Random(73);events=[]
        for node in range(120):
            start=randomizer.randrange(0,49);end=randomizer.randrange(start+1,51);kind=randomizer.randrange(4)
            if kind==0:row=cancel(node,issued=False,tick=end,submitted=randomizer.randrange(end+1))
            elif kind==1:row=cancel(node,start=start,tick=end)
            else:row=event(node,start=start,end=end,completed=True,squashed=kind==3)
            row.update(hart=node%3,lane=node%2);events.append(row)
        g=graph(events,cycles=50);summary,_=profile(g,CLOCK,SOURCE)
        expected={tick for row in events if row.get('issued',True)for tick in range(row['start'],row['end'])}
        self.assertEqual(summary['resources']['unit']['busy_cycles'],len(expected))
        self.assertLessEqual(summary['resources']['unit']['busy_fraction'],1)

    def test_pending_planned_payload_cannot_inflate_roofline(self):
        events=[event(0,start=1,end=4,macs=16),event(1,start=1,end=3,resource='memory',bytes=8),
                cancel(2,issued=False,tick=5,resource='memory',bytes=999)]
        peaks={'unit':{'source':SOURCE,'macs_per_cycle':8},'memory':{'source':SOURCE,'bytes_per_cycle':4}}
        summary,_=profile(graph(events),CLOCK,SOURCE,peaks=peaks,roofline_memory_resource='memory')
        self.assertEqual(summary['regions'][0]['roofline']['arithmetic_intensity_ops_per_byte'],4)
        events[-1]=cancel(2,start=2,tick=5,resource='memory',bytes=999)
        with self.assertRaises(ValueError):profile(graph(events),CLOCK,SOURCE,peaks=peaks,roofline_memory_resource='memory')

class LifecycleRejectionTests(unittest.TestCase):
    def test_malformed_cancellation_records_fail_closed(self):
        mutations=[{'completed':True},{'issued':None},{'cancel_cycle':True},{'cancel_cycle':-1},{'cancel_cycle':21},
            {'end':10},{'start':10},{'submitted':10},{'cancel_reason':''},{'cancel_reason':'  '},
            {'issued':False,'start':4},{'bytes':None},{'macs':True}]
        for change in mutations:
            row=cancel(bytes=8,macs=16);row.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):profile(graph([row]),CLOCK,SOURCE)
        for key in ['completed','issued','cancel_cycle','cancel_reason']:
            row=cancel();row.pop(key)
            with self.subTest(missing=key),self.assertRaises(ValueError):profile(graph([row]),CLOCK,SOURCE)
        for flag in ['completed','cancelled','issued','squashed']:
            row=cancel();row[flag]=1
            with self.subTest(flag=flag),self.assertRaises(ValueError):profile(graph([row]),CLOCK,SOURCE)

    def test_non_cancellation_cannot_smuggle_cancel_metadata(self):
        for field,value in [('cancel_cycle',3),('cancel_reason','redirect')]:
            row=event();row[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):profile(graph([row]),CLOCK,SOURCE)

    def test_all_dependency_shapes_and_cycles_are_validated_before_issue(self):
        for deps in [[0],[999],[True],[1,1],None,{'id':1}]:
            rows=[cancel(0,issued=False,tick=5),cancel(1,issued=False,tick=5)];rows[0]['deps']=deps
            with self.subTest(deps=deps),self.assertRaises(ValueError):profile(graph(rows),CLOCK,SOURCE)
        rows=[cancel(0,issued=False,tick=5),cancel(1,issued=False,tick=5)]
        rows[0]['deps']=[1];rows[1]['deps']=[0]
        with self.assertRaisesRegex(ValueError,'cyclic'):profile(graph(rows),CLOCK,SOURCE)

    def test_deep_canceled_dependency_dag_does_not_require_recursive_stack(self):
        rows=[cancel(node,issued=False,tick=0)for node in range(1500)]
        for node in range(1,len(rows)):rows[node]['deps']=[node-1]
        summary,_=profile(graph(rows,cycles=1),CLOCK,SOURCE)
        self.assertEqual(summary['lifecycle_accounting']['cancelled_before_issue'],1500)
        self.assertEqual(summary['resources']['unit']['busy_cycles'],0)

    def test_canceled_parent_never_unblocks_issued_child(self):
        rows=[cancel(0,issued=False,tick=4),event(1,start=4,end=5)];rows[1]['deps']=[0]
        with self.assertRaisesRegex(ValueError,'unfinished or canceled'):profile(graph(rows),CLOCK,SOURCE)

    def test_direct_counter_and_memory_consumers_reject_invalid_dag(self):
        g=counter_graph([cancel(2,issued=False,tick=5),cancel(3,issued=False,tick=5)])
        g['events'][2]['deps']=[3];g['events'][3]['deps']=[2]
        with self.assertRaisesRegex(ValueError,'cyclic'):observations(g)
        with self.assertRaisesRegex(ValueError,'cyclic'):annotate(g,console(),Image())
        g['memory_transactions']=[]
        with self.assertRaisesRegex(ValueError,'cyclic'):memory_summary(g,{e['id']:e for e in g['events']})

    def test_invalid_unused_event_cannot_hide_outside_observed_region(self):
        g=counter_graph([event(2,start=17,end=19)]);g['events'][2]['squashed']='yes'
        with self.assertRaisesRegex(ValueError,'lifecycle'):annotate(g,console(),Image())

class CanceledCounterRegionTests(unittest.TestCase):
    def test_canceled_and_completed_squashed_reads_are_never_anchors(self):
        for state in ['canceled','squashed']:
            g=counter_graph();node=g['events'][0]
            if state=='canceled':node.update(start=2,end=2,completed=False,issued=False,cancelled=True,cancel_cycle=2,cancel_reason='redirect')
            else:node['squashed']=True
            with self.subTest(state=state),self.assertRaisesRegex(ValueError,'completed instruction'):observations(g)

    def test_legacy_counter_projection_also_excludes_squashed_reads_and_writes(self):
        g=counter_graph();g.pop('counter_read_observations');g['events'][0]['squashed']=True
        with self.assertRaisesRegex(ValueError,'missing or ambiguous'):
            legacy_or_captured(g,console(start=3,end=13),Image(),{0:1,1:1,2:1})
        g=counter_graph([event(2,start=4,end=5,squashed=True)]);g.pop('counter_read_observations')
        class WrongPathWrite(Image):
            def read(self,pc):return(0xb00<<20)|(1<<15)|(1<<12)|0x73 if pc==8 else super().read(pc)
        joined=legacy_or_captured(g,console(start=3,end=13),WrongPathWrite(),{0:1,1:1,2:1})
        self.assertEqual(len(joined['region_boundaries']),1)

    def test_issued_cancel_intersection_is_busy_with_unknown_payload(self):
        result=observed(counter_graph([cancel(2,start=4,tick=9,macs=32)]))
        unit=result['units']['unit'];self.assertEqual(unit['busy_cycles'],5)
        self.assertIsNone(unit['completed_macs']);self.assertTrue(unit['cancelled_mac_payload_unresolved'])
        self.assertEqual(unit['operations_completed_strictly_inside'],0)

    def test_future_issue_cancellation_does_not_poison_earlier_region_payload(self):
        result=observed(counter_graph([cancel(2,start=15,tick=18,submitted=1,macs=32,bytes=64)]))
        unit=result['units']['unit']
        self.assertEqual((unit['busy_cycles'],unit['completed_bytes'],unit['completed_macs']),(0,0,0))
        self.assertEqual(unit['operation_wait_cycles_sum'],10)
        self.assertFalse(unit['cancelled_mac_payload_unresolved']);self.assertFalse(unit['cancelled_byte_payload_unresolved'])
        self.assertEqual(unit['operations_started'],0)

    def test_pending_cancel_counts_wait_without_poisoning_region_completed_work(self):
        result=observed(counter_graph([cancel(2,issued=False,tick=9,submitted=1,macs=999)]))
        unit=result['units']['unit'];self.assertEqual((unit['busy_cycles'],unit['completed_macs']),(0,0))
        self.assertEqual(unit['operation_wait_cycles_sum'],7);self.assertEqual(unit['cancelled_operations'],1)

    def test_partial_cancel_boundary_contact_remains_unknown_without_progress(self):
        result=observed(counter_graph([cancel(2,start=0,tick=2,macs=32)]))
        self.assertEqual(result['units']['unit']['busy_cycles'],0)
        self.assertIsNone(result['units']['unit']['completed_macs'])

    def test_cancellation_on_one_hart_does_not_blank_other_hart_work(self):
        g=counter_graph([cancel(2,start=4,tick=9,macs=32)])
        for node,pc,start,end in [(10,40,2,3),(11,44,12,13)]:
            g['events'].append(event(node,hart=1,start=start,end=end,resource='csr1'))
            g['events'][-1]['pc']=pc
        g['events'].append(event(12,hart=1,start=4,end=8,resource='unit',macs=64));g['events'][-1]['lane']=1
        g['resources'].update(csr1=1,unit=2)
        for seq,node in enumerate([10,11]):
            g['counter_read_observations']['reads'].append(dict(g['counter_read_observations']['reads'][seq],hart=1,node=node,pc=40+seq*4,value=200+seq*10))
        results=profile(annotate(g,console()+console(1,200,210),Image()),CLOCK,SOURCE)[0]['observed_regions']
        self.assertIsNone(results[0]['units']['unit']['completed_macs'])
        self.assertEqual(results[1]['units']['unit']['completed_macs'],64)

    def test_unknown_canceled_payload_cannot_form_a_roofline(self):
        g=counter_graph([cancel(2,start=4,tick=9,resource='memory',bytes=64),event(3,start=3,end=7,macs=16)])
        with self.assertRaises(ValueError):profile(g,CLOCK,SOURCE,peaks={'unit':{'source':SOURCE,'macs_per_cycle':8},
            'memory':{'source':SOURCE,'bytes_per_cycle':4}},roofline_memory_resource='memory')

class AcceptedMemoryCancellationTests(unittest.TestCase):
    def memory_graph(self):
        rows=[event(0,start=0,end=1,resource='cpu',completed=True,squashed=True),
              event(1,start=1,end=6,resource='serial',name='dram.response')]
        rows[1].update(bytes=8,deps=[0])
        stage=dict(node=1,name='response',resource='serial',state='completed',included_in_events=True,
            first_beat_latency=5,launch_interval=8,bytes=8,beat_bytes=8,beat_interval=1,issue_period=1,
            derived_latency=5,derived_interval=8,source=SOURCE,port_source=SOURCE,scheduled_start=1,scheduled_end=6)
        g=graph(rows,cycles=8,memory_transactions=[dict(hart=0,address=0x80000000,access_bytes=8,kind='load',path='dram',stages=[stage])])
        return g

    def test_accepted_memory_survives_squashed_owner_and_keeps_physical_traffic(self):
        g=self.memory_graph();summary,trace=profile(g,CLOCK,SOURCE)
        self.assertEqual(summary['modeled_memory']['rows'][0]['completed_stage_bytes'],8)
        self.assertEqual(summary['modeled_memory']['stage_states']['completed'],1)
        self.assertEqual(summary['resources']['serial']['busy_cycles'],5)
        self.assertEqual(sum(row['cat']=='dependency'for row in trace['traceEvents']),2)

    def test_memory_actor_itself_cannot_be_canceled(self):
        g=self.memory_graph();g['events'][1].update(completed=False,cancelled=True,issued=True,end=4,cancel_cycle=4,cancel_reason='wrongly canceled bus')
        g['memory_transactions'][0]['stages'][0]['state']='inflight'
        with self.assertRaisesRegex(ValueError,'must survive'):profile(g,CLOCK,SOURCE)

    def test_pending_stage_cannot_claim_issued_activity(self):
        g=self.memory_graph();g.update(partial=True,pending_operations=1);g['events'][1]['completed']=False
        g['memory_transactions'][0]['stages'][0]['state']='pending'
        with self.assertRaisesRegex(ValueError,'pending memory'):profile(g,CLOCK,SOURCE)

    def test_boolean_memory_timestamps_never_alias_integer_clock_edges(self):
        g=self.memory_graph();g['memory_transactions'][0]['stages'][0]['scheduled_start']=True
        with self.assertRaisesRegex(ValueError,'timestamps'):profile(g,CLOCK,SOURCE)
        g=self.memory_graph();g['events']=g['events'][:1];g['cycles']=1;g.update(partial=True,pending_operations=1)
        stage=g['memory_transactions'][0]['stages'][0];stage.update(included_in_events=False,state='inflight',scheduled_start=True,scheduled_end=6)
        with self.assertRaisesRegex(ValueError,'frontier'):profile(g,CLOCK,SOURCE)

    def test_memory_receipt_node_map_must_match_original_graph(self):
        g=self.memory_graph();nodes={e['id']:copy.deepcopy(e)for e in g['events']};nodes[1]['bytes']=999
        with self.assertRaisesRegex(ValueError,'node map'):memory_summary(g,nodes)

    def test_malformed_memory_lifecycle_records_raise_validation_errors(self):
        for value in [None,{},'not a transaction']:
            g=self.memory_graph();g['memory_transactions']=[value]
            with self.subTest(transaction=value),self.assertRaises(ValueError):profile(g,CLOCK,SOURCE)
        for value in [None,{},'not a stage']:
            g=self.memory_graph();g['memory_transactions'][0]['stages']=[value]
            with self.subTest(stage=value),self.assertRaises(ValueError):profile(g,CLOCK,SOURCE)
        for key,value in [('state',[]),('name',' '),('resource',None),('source',' '),('port_source',' ')]:
            g=self.memory_graph();g['memory_transactions'][0]['stages'][0][key]=value
            with self.subTest(field=key),self.assertRaises(ValueError):profile(g,CLOCK,SOURCE)

class FrozenCancellationCompatibilityTests(unittest.TestCase):
    def test_cli_binds_lifecycle_source_and_preserves_cancellation_trace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);path=root/'graph.json';output=root/'profile'
            path.write_text(json.dumps(graph([cancel(start=3,tick=8,bytes=64)])))
            result=subprocess.run([sys.executable,'-m','iris_model.report','profile',str(path),
                '--clock-hz',str(CLOCK),'--clock-source',SOURCE,'--output',str(output)],
                cwd=ROOT,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            summary=json.loads((output/'summary.json').read_text())
            timeline=json.loads((output/'timeline.json').read_text())
            lifecycle=ROOT/'iris_model/event_lifecycle.py'
            self.assertEqual(summary['tool_source_sha256']['event_lifecycle.py'],hashlib.sha256(lifecycle.read_bytes()).hexdigest())
            self.assertEqual(summary['graph_sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertIsNone(summary['regions'][0]['units']['unit']['bytes'])
            self.assertEqual([e['ph']for e in timeline['traceEvents']],['X','i'])

    def test_no_cancellation_graph_profiles_remain_byte_identical(self):
        root=ROOT/'build/profiler-before-cancellation-v1'
        for name in ['ordinary','unknown','partial']:
            g=json.loads((root/(name+'.graph.json')).read_text());expected=json.loads((root/(name+'.profile.json')).read_text())
            result=profile(g,expected[0]['clock_hz'],expected[0]['clock_source'])
            self.assertEqual(json.dumps(result).encode(),(root/(name+'.profile.json')).read_bytes(),name)

    def test_actual_engine_cancellation_proof_is_accepted_without_changing_its_bytes(self):
        path=ROOT/'build/frontend-engine-proof-v1/graph.json';before=path.read_bytes();g=json.loads(before)
        summary,trace=profile(g,CLOCK,'actual frozen engine component synthetic proof')
        self.assertEqual(summary['lifecycle_accounting']['cancelled_model_operations'],3)
        self.assertEqual(summary['lifecycle_accounting']['cancelled_before_issue'],1)
        self.assertEqual(summary['lifecycle_accounting']['squashed_completed_model_operations'],1)
        self.assertEqual(sum(e['cat']=='cancellation'for e in trace['traceEvents']),3)
        self.assertEqual(path.read_bytes(),before)

if __name__=='__main__':unittest.main()
