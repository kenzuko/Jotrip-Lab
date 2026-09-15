import unittest
from inbound_intelligence.engine import EvidenceStore,canonicalize_url
from inbound_intelligence.schedule import SCHEDULE
from inbound_intelligence.report_contract import REQUIRED_SECTIONS,validate_report_payload

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.s=EvidenceStore(); self.s.init_schema()
        self.s.create_run("R1","2026-09-14","2026-09-14T05:20:00+07:00","2026-09-14T05:45:00+07:00")
        self.s.create_run("R2","2026-09-15","2026-09-15T05:20:00+07:00","2026-09-15T05:45:00+07:00")
        self.s.add_source("SRC-RED","Reddit","Reddit","Western FIT","en"); self.s.add_source("SRC-TA","Property reviews","Tripadvisor","Luxury","en")
    def test_url_dedup_tracking_and_amp(self):
        a=canonicalize_url("https://www.example.com/thread/amp?utm_source=x&id=7"); b=canonicalize_url("https://example.com/thread?id=7"); self.assertEqual(a,b)
        i1,n1=self.s.upsert_source_item("SRC-RED","https://www.example.com/thread/amp?utm_source=x&id=7","2026-09-14T05:30:00+07:00")
        i2,n2=self.s.upsert_source_item("SRC-RED","https://example.com/thread?id=7","2026-09-15T05:30:00+07:00"); self.assertEqual(i1,i2); self.assertTrue(n1); self.assertFalse(n2)
    def test_same_traveller_thread_is_same_case(self):
        c1,n1=self.s.resolve_case("Reddit","thread-123","travellerA","2026-09-14T05:30:00+07:00"); c2,n2=self.s.resolve_case("Reddit","thread-123","travellerA","2026-09-15T05:30:00+07:00"); self.assertEqual(c1,c2); self.assertTrue(n1); self.assertFalse(n2)
    def _obs(self,run,src,url,casekey,day,stage=2,outcome=None):
        item,_=self.s.upsert_source_item(src,url,day+"T05:30:00+07:00",source_native_id=url); case,_=self.s.resolve_case("x",casekey,casekey,day+"T05:30:00+07:00")
        return self.s.add_observation(run,item,day+"T05:31:00+07:00","BẰNG CHỨNG TRỰC TIẾP","Cao",case_id=case,decision_stage=stage,outcome=outcome,evidence_span="fixture")
    def test_counter_evidence_is_preserved(self):
        self.s.add_signal("SIG-1","Thiếu hoạt động","2026-09-14"); o1=self._obs("R1","SRC-RED","https://r.test/1","c1","2026-09-14"); o2=self._obs("R2","SRC-TA","https://t.test/2","c2","2026-09-15"); self.s.link_signal("SIG-1",o1,"support"); self.s.link_signal("SIG-1",o2,"counter"); v=self.s.signal_vector("SIG-1"); self.assertEqual(v["independent_cases"],1); self.assertEqual(v["counter_evidence"],1)
    def test_five_same_family_cases_do_not_become_grounded(self):
        self.s.add_signal("SIG-2","Narrative","2026-09-14")
        for i in range(5):
            o=self._obs("R1","SRC-RED",f"https://r.test/same{i}",f"same{i}","2026-09-14",stage=2 if i<3 else 8); self.s.link_signal("SIG-2",o)
        self.assertNotEqual(self.s.classify_signal("SIG-2"),"ĐÃ CÓ CƠ SỞ")
    def test_cross_source_signal_can_become_grounded(self):
        self.s.add_signal("SIG-3","Narrative","2026-09-14")
        for i in range(5):
            src="SRC-RED" if i<3 else "SRC-TA"; o=self._obs("R1",src,f"https://x.test/cross{i}",f"cross{i}","2026-09-14",stage=2 if i<3 else 8,outcome="changed" if i==4 else None); self.s.link_signal("SIG-3",o)
        self.assertEqual(self.s.classify_signal("SIG-3"),"ĐÃ CÓ CƠ SỞ")
    def test_blocked_collector_not_interpreted_as_no_signal(self):
        self.s.set_coverage("R2","Korea","Naver","BLOCKED"); self.assertIn("KHÔNG ĐƯỢC SUY",self.s.coverage_interpretation("R2","Korea","Naver"))
    def test_evidence_delta(self):
        self.s.add_signal("SIG-4","Delta","2026-09-14"); o1=self._obs("R1","SRC-RED","https://r.test/d1","d1","2026-09-14"); o2=self._obs("R2","SRC-RED","https://r.test/d2","d2","2026-09-15"); self.s.link_signal("SIG-4",o1); self.s.link_signal("SIG-4",o2); self.assertEqual(self.s.evidence_delta("SIG-4","R1","R2"),{"added":1,"removed":1})
    def test_schedule_is_logically_ordered(self): self.assertTrue(SCHEDULE.validate()); self.assertEqual((SCHEDULE.cutoff.hour,SCHEDULE.cutoff.minute),(5,45))
    def test_report_contract_rejects_fake_history(self):
        payload={"cutoff_at":"2026-09-15T05:45:00+07:00","sections":{s:{} for s in REQUIRED_SECTIONS},"radar":{"Trở ngại mới nổi":{},"Nhu cầu mới nổi":{},"Đối thủ mới nổi":{}},"historical_comparison":{"D-7":"x"},"history_retrievable":False}; self.assertTrue(any("lịch sử" in e for e in validate_report_payload(payload)))

if __name__=="__main__": unittest.main()
