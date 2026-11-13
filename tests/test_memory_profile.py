import copy
import unittest

from iris_model.report import profile


class MemoryProfileTests(unittest.TestCase):
    def graph(self):
        events=[];transactions=[]
        for hart in (0,1):
            events.append(dict(id=hart,hart=hart,name="instruction",resource="cpu",region="kernel",pc=16,
                               start=0,end=2,submitted=0,lane=0,bytes=0,macs=0,deps=[]))
        for hart,start in [(0,2),(1,10)]:
            node=hart+2
            events.append(dict(id=node,hart=hart,name="dram.response",resource="serial",region="kernel",pc=16,
                               start=start,end=start+5,submitted=0,lane=0,bytes=8,macs=0,deps=[hart]))
            transactions.append(dict(hart=hart,address=0x80000000+hart*64,access_bytes=8,kind="load",path="dram",
                stages=[dict(node=node,name="response",resource="serial",state="completed",included_in_events=True,
                    first_beat_latency=5,launch_interval=8,bytes=8,beat_bytes=8,beat_interval=1,
                    issue_period=1,derived_latency=5,derived_interval=8,source="synthetic",port_source="synthetic",
                    scheduled_start=start,scheduled_end=start+5)]))
        return dict(schema_version=1,status="experimental_uncalibrated",harts=3,cycles=15,
                    resources={"cpu":2,"serial":1},events=events,memory_transactions=transactions,
                    traffic_accounting="not_instrumented",arithmetic_accounting="not_instrumented")

    def test_waits_exclude_dependency_time_and_preserve_per_hart_stage_bytes(self):
        summary,_=profile(self.graph(),100,"synthetic")
        memory=summary["modeled_memory"]
        self.assertEqual(memory["stage_states"],{"completed":2,"inflight":0,"pending":0})
        self.assertEqual([r["port_queue_wait_cycles_sum"] for r in memory["rows"]],[0,8])
        self.assertEqual([r["completed_stage_bytes"] for r in memory["rows"]],[8,8])
        self.assertEqual([r["clock_alignment_cycles_sum"] for r in memory["rows"]],[0,0])
        # Modeled packets do not silently become instrumented application traffic.
        self.assertIsNone(summary["regions"][0]["units"]["serial"]["bytes"])
        self.assertIsNone(summary["regions"][0]["roofline"])
        self.assertFalse(memory["hardware_certified"])

    def test_pending_and_frontier_nodes_do_not_claim_completed_traffic(self):
        graph=self.graph();graph.update(partial=True,pending_operations=2)
        for node,state,start,end in [(4,"pending",None,None),(5,"inflight",15,20)]:
            tx=copy.deepcopy(graph["memory_transactions"][0]);tx["hart"]=2
            tx["stages"][0].update(node=node,state=state,included_in_events=False,scheduled_start=start,scheduled_end=end)
            graph["memory_transactions"].append(tx)
        summary,_=profile(graph,100,"synthetic")
        memory=summary["modeled_memory"]
        self.assertEqual(memory["stage_states"],{"completed":2,"inflight":1,"pending":1})
        self.assertEqual(sum(r["completed_stage_bytes"] for r in memory["rows"]),16)
        graph["memory_transactions"][-1]["stages"][0]["scheduled_start"]=14
        with self.assertRaisesRegex(ValueError,"frontier"):profile(graph,100,"synthetic")

    def test_receipt_cannot_fabricate_duration_clock_or_bytes(self):
        for field,value in [("derived_latency",4),("scheduled_end",8),("bytes",16),("issue_period",3),
                            ("state","pending"),("source","")]:
            graph=self.graph();graph["memory_transactions"][0]["stages"][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):profile(graph,100,"synthetic")

    def test_duplicate_stage_identity_or_unfinished_parent_is_rejected(self):
        graph=self.graph();graph["memory_transactions"].append(copy.deepcopy(graph["memory_transactions"][0]))
        with self.assertRaisesRegex(ValueError,"duplicate"):profile(graph,100,"synthetic")
        graph=self.graph();graph.update(partial=True,pending_operations=1);graph["events"][0]["completed"]=False
        with self.assertRaisesRegex(ValueError,"unfinished"):profile(graph,100,"synthetic")

    def test_receiving_clock_alignment_is_separate_from_port_wait(self):
        graph=self.graph();graph["memory_transactions"]=graph["memory_transactions"][:1]
        graph["events"]=[graph["events"][0],graph["events"][2]]
        graph["events"][1].update(start=3,end=9)
        stage=graph["memory_transactions"][0]["stages"][0]
        stage.update(issue_period=3,scheduled_start=3,scheduled_end=9)
        summary,_=profile(graph,100,"synthetic")
        row=summary["modeled_memory"]["rows"][0]
        self.assertEqual(row["clock_alignment_cycles_sum"],1)
        self.assertEqual(row["port_queue_wait_cycles_sum"],0)


if __name__=="__main__":unittest.main()
