import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest

from iris_model.guest_regions import Instructions, annotate, fixture_clocks, verify_run
from iris_model.report import profile

READ=(0xb00<<20)|(2<<12)|(5<<7)|0x73


class Image:
    def __init__(self): self.code={0:READ,4:0x13,8:0x13,12:READ}
    def read(self,pc): return self.code[pc]


class GuestRegionsTests(unittest.TestCase):
    def graph(self):
        return {"schema_version":1,"harts":1,"cycles":5,"status":"experimental_uncalibrated",
                "timing_mode":"uncalibrated-integration-fixture","base_clock_hz":100,"clock_source":"test",
                "hart_cycle_dividers":[1],"resources":{"scalar0":1},
                "events":[{"id":i,"hart":0,"name":"instruction","resource":"scalar0","pc":i*4,
                           "start":i+1,"end":i+2,"submitted":i+1,"lane":0,"completed":True,
                           "bytes":0,"macs":0,"deps":[i-1] if i else []} for i in range(4)]}

    def console(self,start=2,end=5,name="kernel"):
        return "IRIS_REGION "+json.dumps({"case_id":name,"region":"compute","hart":0,
                                         "start_cycle":start,"end_cycle":end})+"\n"

    def test_actual_completed_reads_supply_exact_region_duration(self):
        graph=annotate(self.graph(),self.console(),Image(),{0:1})
        summary,_=profile(graph,100,"test")
        region=next(r for r in summary["regions"] if r["region"]=="kernel::compute")
        self.assertEqual((region["start_cycle"],region["end_cycle"],region["cycles"]),(2,5,3))
        self.assertEqual(region["guest_mcycle_delta"],3)
        self.assertEqual(region["units"]["scalar0"]["busy_fraction"],1)
        self.assertIn("completed CSR",region["region_boundary_source"])

    def test_missing_or_ambiguous_counter_values_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"missing or ambiguous"):
            annotate(self.graph(),self.console(start=3),Image(),{0:1})
        graph=self.graph();duplicate=dict(graph["events"][0],id=20);graph["events"].append(duplicate)
        with self.assertRaisesRegex(ValueError,"ambiguous"):
            annotate(graph,self.console(),Image(),{0:1})

    def test_counter_writes_and_inhibit_changes_are_rejected(self):
        for csr in (0xb00,0xb80,0x321,0x320):
            image=Image();image.code[4]=(csr<<20)|(1<<15)|(1<<12)|0x73
            with self.subTest(csr=csr),self.assertRaises(ValueError):
                annotate(self.graph(),self.console(),image,{0:1})
        image=Image();image.code[4]=(0x320<<20)|(1<<12)|0x73
        self.assertEqual(len(annotate(self.graph(),self.console(),image,{0:1})["region_boundaries"]),1)

    def test_wfi_and_divider_proof_is_mandatory(self):
        good="purpose uncalibrated-integration-fixture\nbase_hz 100\nhart 0 1 1\n"
        self.assertEqual(fixture_clocks(good,self.graph()),{0:1})
        for bad in (good.replace("0 1 1","0 1 0"),good.replace("0 1 1","0 2 1"),good.replace("100","200")):
            with self.subTest(fixture=bad),self.assertRaises(ValueError):fixture_clocks(bad,self.graph())

    def test_overlap_requires_explicit_nesting_support(self):
        with self.assertRaisesRegex(ValueError,"overlapping"):
            annotate(self.graph(),self.console()+self.console(name="nested"),Image(),{0:1})

    def test_riscv_elf_reader_checks_real_executable_bounds(self):
        header=bytearray(64);header[:7]=b"\x7fELF\x02\x01\x01"
        struct.pack_into("<HHI",header,16,2,243,1);struct.pack_into("<Q",header,32,64)
        struct.pack_into("<HHH",header,52,64,56,1)
        ph=struct.pack("<IIQQQQQQ",1,5,256,0x80000000,0x80000000,4,4096,4096)
        data=bytes(header)+ph;data+=bytes(256-len(data))+struct.pack("<I",READ)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"guest.elf";path.write_bytes(data)
            image=Instructions(path)
            self.assertEqual(image.read(0x80000000),READ)
            with self.assertRaisesRegex(ValueError,"missing"):image.read(0x80000100)
            path.write_bytes(data[:100])
            with self.assertRaisesRegex(ValueError,"headers"):Instructions(path)

    def mixed_receipt(self):
        rows=[{"case_id":"mixed","region":"kernel","hart":h,
               "role":"vme.compute" if h<2 else "vector.copy"} for h in range(3)]
        receipt={"status":"passed_mixed_zephyr_smp_live_fixture","exit_status":0,
                 "timed_out":False,"errors":[],"checksums_independent":True,"physical_boot":True,
                 "harts":[0,1,2],"regions":rows,
                 "vme_ownership_abi":"iris_vme_enable before measured VME region on compute harts only"}
        console="".join("IRIS_REGION "+json.dumps(row)+"\n" for row in rows)
        return receipt,console

    def test_mixed_run_admits_checked_regions_with_explicit_ownership(self):
        receipt,console=self.mixed_receipt()
        self.assertEqual(verify_run(receipt,console),receipt["regions"])
        scalar=copy.deepcopy(receipt);scalar["status"]="passed_scalar_zephyr_smp_live_fixture"
        self.assertEqual(verify_run(scalar,console),receipt["regions"])

    def test_failed_unchecked_or_altered_region_evidence_is_rejected(self):
        receipt,console=self.mixed_receipt()
        for key,value in [("exit_status",1),("timed_out",True),("errors",["failed"]),
                          ("checksums_independent",False),("physical_boot",False),
                          ("status","prepared")]:
            bad=copy.deepcopy(receipt);bad[key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,"successful"):
                verify_run(bad,console)
        bad=copy.deepcopy(receipt);bad["regions"].pop()
        with self.assertRaisesRegex(ValueError,"disagree"):verify_run(bad,console)
        with self.assertRaisesRegex(ValueError,"disagree"):verify_run(receipt,console+console)

    def test_mixed_evidence_cannot_assign_vme_to_rocket_or_omit_ownership(self):
        receipt,console=self.mixed_receipt()
        for update in (lambda r:r.pop("vme_ownership_abi"),lambda r:r.update(harts=[0,1]),
                       lambda r:r["regions"][2].update(role="vme.compute")):
            bad=copy.deepcopy(receipt);update(bad)
            text="".join("IRIS_REGION "+json.dumps(row)+"\n" for row in bad["regions"])
            with self.assertRaises(ValueError):verify_run(bad,text)


if __name__=="__main__":unittest.main()
