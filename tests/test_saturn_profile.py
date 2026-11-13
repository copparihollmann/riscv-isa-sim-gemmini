import copy
import math
import unittest

from iris_model.saturn_profile import COUNTERS, OCCUPANCY, STATES, profile


FIELDS = list(STATES + COUNTERS + OCCUPANCY)
INDEX = {name:i for i,name in enumerate(FIELDS)}
ALL = (1 << len(FIELDS))-1


def schema():
    return {'schema':'iris.saturn_qualified_activity_projection.v1',
        'record_layout':['hart','source_edge','tb','known_mask']+FIELDS,
        'state_interval':'Pre-edge state describes the preceding supplied source interval.'}


def contract():
    def config(harts,dlen,vme):
        return {'configured_harts':harts,'VLEN_bits':256,'DLEN_bits':dlen,
            'metrics':{'VME':{'peak_eligible_MAC_per_source_edge':256,'peak_scope':'eligible full-mask cells; not a sustained guarantee'} if vme else None,
                       'RVV_peak_reason':'FU/op/dtype proof unavailable'}}
    return {'schema':'iris.saturn_activity_semantic_contract.v1',
            'profiles':{'compute':config([0,1],128,True),'rocket':config([2],256,False)}}


def records():
    rows=[]
    for edge,tb in enumerate([3,5,7,9]):
        for hart in range(3):
            values=[0]*len(FIELDS)
            known=1 if edge==0 else ALL
            if edge==0: values[INDEX['reset']]=1
            if edge==1:
                for name in ['VRF_scrub','backend_busy_source','dispatch_accept']:values[INDEX[name]]=1
                values[INDEX['RVV_integer_pipe_busy' if hart<2 else 'RVV_unified_pipe_busy']]=1
                values[INDEX['VMU_SIQ_occupancy']]=2
                if hart<2:
                    for name in ['VME_busy_union','VME_macro_accept','VME_micro_issue']:values[INDEX[name]]=1
                    values[INDEX['VME_INT8_MAC_accept']]=4;values[INDEX['VME_INT8_MAC_complete']]=4
                    values[INDEX['VME_FP8_MAC_accept']]=16;values[INDEX['VME_VRF_write_bits']]=128
            if edge==2 and hart<2:
                values[INDEX['VME_busy_union']]=1;values[INDEX['VME_FP8_MAC_complete']]=16
            rows.append([hart,edge,tb,known]+values)
    return rows


def result(regions=(),rows=None):
    return profile(records() if rows is None else rows,schema(),contract(),1e9,'source CLOCK_PERIOD=1ns',regions)


class ActivityProfileTests(unittest.TestCase):
    def test_tail_activity_is_separate_from_backend_and_mac_accept_completion(self):
        summary,trace=result();h=summary['regions'][0]
        self.assertEqual(summary['frames_per_hart'],[4,4,4])
        self.assertEqual(h['states']['backend_busy_source']['active_intervals'],1)
        self.assertEqual(h['states']['VME_busy_union']['active_intervals'],2)
        self.assertAlmostEqual(h['states']['VME_busy_union']['active_fraction_of_known_intervals'],2/3)
        self.assertEqual(h['counts']['VME_FP8_MAC_accept']['sum'],16)
        self.assertEqual(h['counts']['VME_FP8_MAC_complete']['sum'],16)
        accepted=[e for e in trace['traceEvents'] if e['pid']==0 and e['name']=='VME_FP8_MAC_accept']
        complete=[e for e in trace['traceEvents'] if e['pid']==0 and e['name']=='VME_FP8_MAC_complete']
        self.assertEqual(accepted[0]['ts'],0.005);self.assertEqual(complete[0]['ts'],0.007)
        busy=[e for e in trace['traceEvents'] if e['pid']==0 and e['name']=='VME_busy_union']
        self.assertEqual((busy[0]['ts'],busy[0]['dur']),(0.003,0.004))
        self.assertIsNone(h['roofline']);self.assertIsNone(h['memory_bytes'])
        self.assertFalse(summary['FPGA_or_full_timing_certified'])

    def test_clipped_region_preserves_prior_inflight_completions_and_time_coverage(self):
        summary,trace=result([{'id':'roi','hart':0,'start_tb':6,'end_tb':9,'source':'explicit fixture boundary'}])
        h=next(h for h in summary['regions'] if h['region']=='roi')
        self.assertEqual(h['counts']['VME_FP8_MAC_accept']['sum'],0)
        self.assertEqual(h['counts']['VME_FP8_MAC_complete']['sum'],16)
        self.assertEqual(h['states']['VME_busy_union']['known_tb_ticks'],3)
        self.assertEqual(h['states']['VME_busy_union']['active_tb_ticks'],1)
        self.assertAlmostEqual(h['states']['VME_busy_union']['active_fraction_of_known_tb_ticks'],1/3)
        events=[e for e in trace['traceEvents'] if e.get('args',{}).get('region')=='roi' and e['name']=='VME_busy_union']
        self.assertEqual((events[0]['ts'],events[0]['dur']),(0.006,0.001))

    def test_unknown_state_is_a_gap_not_idle_and_unknown_payload_cannot_leak(self):
        rows=records();row=next(r for r in rows if r[:2]==[0,2]);row[3]&=~(1<<INDEX['VME_busy_union']);row[4+INDEX['VME_busy_union']]=0
        summary,trace=result(rows=rows);state=summary['regions'][0]['states']['VME_busy_union']
        self.assertEqual((state['unknown_intervals'],state['known_intervals'],state['active_intervals']),(1,2,1))
        self.assertEqual(state['active_fraction_of_known_intervals'],0.5)
        unknown=[e for e in trace['traceEvents'] if e['name']=='VME_busy_union unknown' and e['pid']==0]
        self.assertEqual(unknown[0]['dur'],0.002)
        row[4+INDEX['VME_busy_union']]=1
        with self.assertRaisesRegex(ValueError,'placeholder'):result(rows=rows)

    def test_unit_absence_and_cpu_or_memory_metrics_are_not_fabricated(self):
        summary,_=result();h=summary['regions'][2]
        self.assertFalse(h['VME_present']);self.assertIsNone(h['VME_peak_eligible_MACs_per_source_edge'])
        self.assertIsNone(h['RVV_peak_elements_per_edge']);self.assertIsNone(h['roofline'])
        self.assertIn('CPU_utilization',h['unsupported_metrics'])
        rows=records();row=next(r for r in rows if r[:2]==[2,1]);row[4+INDEX['VME_busy_union']]=1
        with self.assertRaisesRegex(ValueError,'without the unit'):result(rows=rows)

    def test_missing_reset_bad_mask_bool_negative_and_capacity_corruptions_refuse(self):
        for kind in ['reset','mask','bool','negative','MAC','reset_work','edge','clock']:
            rows=records()
            if kind=='reset': rows[0][4+INDEX['reset']]=0;rows[0][3]=ALL
            if kind=='mask':rows[0][3]=1<<len(FIELDS)
            if kind=='bool':rows[0][0]=False
            if kind=='negative':rows[0][2]=-1
            if kind=='MAC':rows[3][4+INDEX['VME_FP8_MAC_accept']]=257
            if kind=='reset_work':rows[0][3]=ALL
            if kind=='edge':rows[3][1]=2
            if kind=='clock':rows[3][2]=2
            with self.subTest(kind=kind),self.assertRaises(ValueError):result(rows=rows)

    def test_missing_hart_or_unproven_clock_or_regions_refuse(self):
        with self.assertRaisesRegex(ValueError,'Missing configured hart'):result(rows=[r for r in records() if r[0]!=2])
        for clock in [0,-1,True,math.nan,math.inf]:
            with self.subTest(clock=clock),self.assertRaisesRegex(ValueError,'clock frequency'):
                profile(records(),schema(),contract(),clock,'source')
        for regions in [[{'id':'roi','hart':0,'start_tb':1,'end_tb':5,'source':'outside'}],
                        [{'id':'roi','hart':True,'start_tb':3,'end_tb':5,'source':'bad'}],
                        [{'id':'capture','hart':0,'start_tb':3,'end_tb':5,'source':'bad'}],
                        [{'id':'roi','hart':0,'start_tb':3,'end_tb':5,'source':True}]]:
            with self.subTest(regions=regions),self.assertRaises(ValueError):result(regions)


if __name__=='__main__':unittest.main()
