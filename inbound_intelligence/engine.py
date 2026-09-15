from __future__ import annotations
import hashlib, sqlite3, uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

TRACKING_KEYS={"utm_source","utm_medium","utm_campaign","utm_term","utm_content","gclid","fbclid","mc_cid","mc_eid","ref","ref_src"}

def canonicalize_url(url:str)->str:
    p=urlsplit(url.strip()); host=p.netloc.lower()
    if host.startswith("www."): host=host[4:]
    path=p.path.rstrip("/") or "/"
    if path.endswith("/amp"): path=path[:-4] or "/"
    query=[(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if k.lower() not in TRACKING_KEYS]; query.sort()
    return urlunsplit((p.scheme.lower() or "https",host,path,urlencode(query),""))

def stable_hash(value:str)->str: return hashlib.sha256(value.encode("utf-8")).hexdigest()

class EvidenceStore:
    def __init__(self,db_path=":memory:"):
        self.conn=sqlite3.connect(db_path); self.conn.row_factory=sqlite3.Row; self.conn.execute("PRAGMA foreign_keys = ON")
    def init_schema(self): self.conn.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
    def create_run(self,run_id,report_date,collector_started_at,cutoff_at,spec_version="1.1-lab",status="collecting"):
        self.conn.execute("INSERT INTO runs(run_id,report_date,collector_started_at,cutoff_at,status,spec_version) VALUES(?,?,?,?,?,?)",(run_id,report_date,collector_started_at,cutoff_at,status,spec_version)); self.conn.commit()
    def add_source(self,source_id,source_family,platform,market=None,language=None):
        self.conn.execute("INSERT OR REPLACE INTO sources(source_id,source_family,platform,market,language) VALUES(?,?,?,?,?)",(source_id,source_family,platform,market,language)); self.conn.commit()
    def upsert_source_item(self,source_id,url,observed_at,source_native_id=None,published_at=None,content="",verification_status="verified"):
        canon=canonicalize_url(url); row=None
        if source_native_id: row=self.conn.execute("SELECT * FROM source_items WHERE source_id=? AND source_native_id=?",(source_id,source_native_id)).fetchone()
        if not row: row=self.conn.execute("SELECT * FROM source_items WHERE canonical_url=?",(canon,)).fetchone()
        if row:
            self.conn.execute("UPDATE source_items SET observed_last_at=?,verification_status=? WHERE item_id=?",(observed_at,verification_status,row["item_id"])); self.conn.commit(); return row["item_id"],False
        item_id="ITEM-"+uuid.uuid4().hex[:16]
        self.conn.execute("INSERT INTO source_items(item_id,source_id,source_native_id,canonical_url,published_at,observed_first_at,observed_last_at,content_hash,verification_status) VALUES(?,?,?,?,?,?,?,?,?)",(item_id,source_id,source_native_id,canon,published_at,observed_at,observed_at,stable_hash(content) if content else None,verification_status)); self.conn.commit(); return item_id,True
    def resolve_case(self,platform,thread_id,traveller_handle,observed_at,market=None,language=None,cohort=None):
        traveller_hash=stable_hash(traveller_handle.strip().lower()) if traveller_handle else None
        case_key=stable_hash("|".join([platform.lower(),str(thread_id),traveller_hash or "anon"]))
        row=self.conn.execute("SELECT * FROM traveller_cases WHERE case_key=?",(case_key,)).fetchone()
        if row:
            self.conn.execute("UPDATE traveller_cases SET last_seen_at=?,market=COALESCE(?,market),language=COALESCE(?,language),cohort=COALESCE(?,cohort) WHERE case_id=?",(observed_at,market,language,cohort,row["case_id"])); self.conn.commit(); return row["case_id"],False
        case_id="CASE-"+uuid.uuid4().hex[:16]
        self.conn.execute("INSERT INTO traveller_cases(case_id,case_key,market,language,cohort,traveller_hash,first_seen_at,last_seen_at) VALUES(?,?,?,?,?,?,?,?)",(case_id,case_key,market,language,cohort,traveller_hash,observed_at,observed_at)); self.conn.commit(); return case_id,True
    def add_observation(self,run_id,item_id,created_at,evidence_label,evidence_strength,case_id=None,decision_stage=None,outcome=None,evidence_span=None,**kwargs):
        obs_id="OBS-"+uuid.uuid4().hex[:16]; cols=["observation_id","run_id","case_id","item_id","evidence_label","evidence_strength","decision_stage","outcome","evidence_span","created_at"]; vals=[obs_id,run_id,case_id,item_id,evidence_label,evidence_strength,decision_stage,outcome,evidence_span,created_at]
        for k in ["property_name","planned_los","actual_los","want","barrier","hidden_anxiety","competitor","orientation","off_property_propensity"]:
            if k in kwargs: cols.append(k); vals.append(kwargs[k])
        self.conn.execute(f"INSERT INTO observations({','.join(cols)}) VALUES({','.join('?' for _ in cols)})",vals); self.conn.commit(); return obs_id
    def add_signal(self,signal_id,name_vi,observed_at,status="MỚI"):
        self.conn.execute("INSERT INTO signals(signal_id,name_vi,status,first_seen_at,last_seen_at) VALUES(?,?,?,?,?) ON CONFLICT(signal_id) DO UPDATE SET last_seen_at=excluded.last_seen_at",(signal_id,name_vi,status,observed_at,observed_at)); self.conn.commit()
    def link_signal(self,signal_id,observation_id,direction="support"):
        self.conn.execute("INSERT OR REPLACE INTO signal_evidence(signal_id,observation_id,direction) VALUES(?,?,?)",(signal_id,observation_id,direction)); self.conn.commit()
    def set_coverage(self,run_id,market,source_family,collector_status,candidates_seen=None,origins_opened=None,verified_items=None,notes=None):
        self.conn.execute("INSERT OR REPLACE INTO coverage(run_id,market,source_family,collector_status,candidates_seen,origins_opened,verified_items,notes) VALUES(?,?,?,?,?,?,?,?)",(run_id,market,source_family,collector_status,candidates_seen,origins_opened,verified_items,notes)); self.conn.commit()
    def signal_vector(self,signal_id):
        rows=self.conn.execute("SELECT o.case_id,o.decision_stage,o.outcome,o.created_at,se.direction,s.source_family FROM signal_evidence se JOIN observations o ON o.observation_id=se.observation_id JOIN source_items i ON i.item_id=o.item_id JOIN sources s ON s.source_id=i.source_id WHERE se.signal_id=?",(signal_id,)).fetchall(); support=[r for r in rows if r["direction"]=="support"]; counter=[r for r in rows if r["direction"]=="counter"]
        return {"independent_cases":len({r['case_id'] for r in support if r['case_id']}),"source_families":len({r['source_family'] for r in support}),"decision_stages":len({r['decision_stage'] for r in support if r['decision_stage'] is not None}),"outcome_cases":len({r['case_id'] for r in support if r['case_id'] and r['outcome']}),"persistence_days":len({str(r['created_at'])[:10] for r in support}),"counter_evidence":len(counter)}
    def classify_signal(self,signal_id):
        v=self.signal_vector(signal_id)
        if v["independent_cases"]>=10 and v["source_families"]>=2 and v["persistence_days"]>=2 and (v["decision_stages"]>=2 or v["outcome_cases"]>=2): return "ĐÃ CÓ CƠ SỞ"
        if v["independent_cases"]>=5 and v["source_families"]>=2 and (v["decision_stages"]>=2 or v["outcome_cases"]>=1): return "ĐÃ CÓ CƠ SỞ"
        if (v["independent_cases"]>=3 and v["source_families"]>=2) or (v["independent_cases"]>=3 and v["persistence_days"]>=2): return "THEO DÕI"
        return "MỚI"
    def coverage_interpretation(self,run_id,market,source_family):
        row=self.conn.execute("SELECT collector_status FROM coverage WHERE run_id=? AND market=? AND source_family=?",(run_id,market,source_family)).fetchone()
        if not row: return "CHƯA QUAN SÁT ĐƯỢC"
        status=row["collector_status"]
        if status=="OK": return "ĐÃ QUÉT"
        if status=="NO_ELIGIBLE_ITEM": return "ĐÃ QUÉT - KHÔNG CÓ ITEM ĐỦ ĐIỀU KIỆN"
        return f"KHÔNG ĐƯỢC SUY THÀNH KHÔNG CÓ TÍN HIỆU - {status}"
    def evidence_delta(self,signal_id,older_run_id,newer_run_id):
        def ids(run_id): return {r[0] for r in self.conn.execute("SELECT se.observation_id FROM signal_evidence se JOIN observations o ON o.observation_id=se.observation_id WHERE se.signal_id=? AND o.run_id=?",(signal_id,run_id))}
        old,new=ids(older_run_id),ids(newer_run_id); return {"added":len(new-old),"removed":len(old-new)}
