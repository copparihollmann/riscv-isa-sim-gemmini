"""Actual edge work has payload without an invented occupied cycle."""
import copy
import unittest

from iris_model.counter_regions import annotate
from iris_model.event_lifecycle import validate_events
from iris_model.report import profile
from test_cancellation_profile import CLOCK, SOURCE, Image, counter_graph, console, event, graph


def point(node=2,tick=7,**extra):
    row=event(node,submitted=tick,start=tick,end=tick,completed=True,physical_acceptance=True,
        physical_edge=True,physical_source=SOURCE,completion_policy='same-source-edge',pc_known=False,pc=0)
    row.update(extra);return row


class PhysicalPointTests(unittest.TestCase):
    def test_completed_edge_counts_work_without_occupancy_queue_wait_or_fake_duration(self):
        g=graph([point(tick=0,macs=4,bytes=8)],cycles=0)
        summary,trace=profile(g,CLOCK,SOURCE,[(0,16,'wrong_placeholder_symbol')])
        unit=summary['regions'][0]['units']['unit']
        self.assertEqual((unit['busy_cycles'],unit['macs'],unit['bytes']),(0,4,8))
        self.assertEqual(summary['regions'][0]['operation_queue_wait_cycles_sum'],0)
        self.assertEqual(summary['resources']['unit']['physical_edge_operations'],1)
        self.assertEqual(summary['functions'][0]['function'],None)
        self.assertEqual(summary['functions'][0]['active_cycles'],0)
        self.assertEqual(len(trace['traceEvents']),1);entry=trace['traceEvents'][0]
        self.assertEqual((entry['ph'],entry['cat'],entry['ts']),('i','physical source edge',0))
        self.assertNotIn('dur',entry);self.assertFalse(entry['args']['pc_known']);self.assertIsNone(entry['args']['pc'])

    def test_captured_region_uses_halfopen_point_boundary_and_preserves_zero_function_span(self):
        g=counter_graph([point(2,tick=2,macs=10),point(3,tick=7,macs=19),point(4,tick=12,macs=99)])
        measured=annotate(g,console(),Image())
        summary,_=profile(measured,CLOCK,SOURCE,[(0,64,'not_an_owner')])
        region=summary['observed_regions'][0];unit=region['units']['unit']
        self.assertEqual((unit['completed_macs'],unit['busy_cycles']),(29,0))
        self.assertFalse(unit['boundary_mac_completion_unresolved'])
        self.assertEqual(unit['physical_edge_operations_completed'],2)
        self.assertEqual(unit['operations_completed_strictly_inside'],1)
        self.assertEqual(unit['operations_completed_in_region'],2)
        fn=next(f for f in region['functions'] if 'unit' in f['resources'])
        self.assertIsNone(fn['function']);self.assertEqual(fn['model_operations'],2);self.assertEqual(fn['active_cycles'],0)

    def test_completed_span_boundary_ties_stay_unresolved(self):
        g=counter_graph([point(2,tick=2,macs=10),event(3,submitted=0,start=1,end=2,macs=2)])
        summary,_=profile(annotate(g,console(),Image()),CLOCK,SOURCE)
        unit=summary['observed_regions'][0]['units']['unit']
        self.assertIsNone(unit['completed_macs']);self.assertTrue(unit['boundary_mac_completion_unresolved'])

    def test_source_dependencies_allow_completed_same_edge_parents_not_unfinished_work(self):
        validate_events(graph([point(2,tick=3),point(3,tick=3,deps=[2])]))
        g=graph([event(0,start=1,end=3,completed=False),point(2,tick=3,deps=[0])],partial=True,pending_operations=1)
        with self.assertRaisesRegex(ValueError,'unfinished'):validate_events(g)

    def test_contradictory_or_unsourced_point_contracts_refuse(self):
        changes=[{'physical_edge':False},{'physical_edge':'yes'},{'physical_acceptance':False},
            {'physical_source':''},{'pc_known':None},{'pc_known':False,'pc':4},
            {'completion_policy':'matching-source-response'},{'submitted':6},{'start':6},
            {'end':8},{'completed':False},{'issued':False},{'cancelled':True},
            {'macs':True},{'bytes':-1}]
        for change in changes:
            row=point();row.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):validate_events(graph([row]))
        row=point();del row['completed']
        with self.assertRaises(ValueError):validate_events(graph([row]))

    def test_zero_elapsed_accepted_request_is_pending_only_at_current_partial_snapshot(self):
        row=point(tick=7,bytes=64,completed=False,physical_edge=False,completion_policy='matching-source-response')
        g=graph([row],cycles=7,partial=True,pending_operations=1)
        summary,trace=profile(g,CLOCK,SOURCE)
        unit=summary['regions'][0]['units']['unit']
        self.assertEqual(unit['busy_cycles'],0);self.assertEqual(unit['incomplete_operations'],1)
        self.assertIsNone(unit['bytes'])
        self.assertEqual(trace['traceEvents'][0]['cat'],'physical source acceptance')
        self.assertFalse(trace['traceEvents'][0]['args']['completed'])
        with self.assertRaises(ValueError):validate_events(graph([row],cycles=8,partial=True,pending_operations=1))
        with self.assertRaises(ValueError):validate_events(graph([row],cycles=7))
        row['completed']=True
        with self.assertRaises(ValueError):validate_events(graph([row],cycles=7))

    def test_actual_counter_read_requires_known_instruction_pc(self):
        g=counter_graph();g['events'][0]['pc_known']=False
        with self.assertRaisesRegex(ValueError,'counter observation'):
            annotate(g,console(),Image())


if __name__=='__main__':unittest.main()
