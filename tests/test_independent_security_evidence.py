import copy, hashlib, io, json, unittest, zipfile
from ai_product_factory.independent_security_evidence import REPO, OWNER_WORKFLOW, REVIEWED_FIXTURES, WORKFLOWS, TRUSTED_SCANNER_FILES, TRUSTED_SCANNER_SHA, SecurityEvidenceBlocked, verify_existing_secrets_dependencies, _scan_run
SHA="a"*40; TREE="b"*40; ROOT="/repos/"+REPO
def env(): return {"GITHUB_ACTIONS":"true","GITHUB_REPOSITORY":REPO,"GITHUB_EVENT_NAME":"workflow_run","GITHUB_REF":"refs/heads/main","GITHUB_WORKFLOW_REF":REPO+"/"+OWNER_WORKFLOW+"@refs/heads/main","GITHUB_RUN_ID":"7","GITHUB_TOKEN":"x"}
def receipt(k):
 if k=="gitleaks": return {"schema":"factory-block1-complete-tracked-tree-gitleaks-v1","assessed_commit":SHA,"tree_oid":TREE,"source_digest":hashlib.sha256((SHA+":"+TREE).encode()).hexdigest(),"scanner":"gitleaks","scanner_version":"8.24.3","scope":"complete_committed_tree_not_all_historical_git_commits","tracked_files_scanned":100,"scan_passed":True,"zero_unreviewed_findings":True,"trusted_builtin_rules":True,"repository_allowlists_ignored":True,"raw_finding_count":8,"reviewed_source_blob_pinned_fixtures":[{"path":p,"line":l,"rule_id":r} for p,l,r in REVIEWED_FIXTURES],"all_history_scanned":False,"secrets_dependencies_certified":False,"block1_certified":False,"paid_calls":0,"production_writes":0}
 return {"schema":"factory-block1-npm-advisory-evidence-v1","sha":SHA,"scope":"production_dependencies_lockfile","scanner":"npm audit","valid_report":True,"passed":True,"high":0,"critical":0,"scanner_exit_code":0,"block1_certified":False}
def z(k,m):
 o=io.BytesIO()
 with zipfile.ZipFile(o,"w") as a:
  a.writestr(m,json.dumps(receipt(k)))
  if k=="gitleaks":a.writestr("block1-credential-exposure-receipt.json",json.dumps({"schema":"factory-block1-credential-exposure-v4","scope":"static-import-reachability-for-client-public-health-and-per-http-handler-guards-not-runtime-authentication","console_files_scanned":1,"client_entrypoints_scanned":1,"route_handlers_scanned":1,"public_surface_roots":["apps/console/app/api/health/route.ts"],"credential_exposure_detected":False,"privileged_values_read":False,"security_certified":False,"writes":0,"paid_calls":0,"findings":[]}))
 return o.getvalue()
def fixture():
 v={ROOT+"/git/ref/heads/main":{"object":{"sha":SHA}},ROOT+"/actions/runs/7":{"id":7,"name":"Factory autonomous runner","path":OWNER_WORKFLOW,"event":"workflow_run","head_sha":SHA,"head_branch":"main","run_attempt":1},ROOT+"/git/commits/"+SHA:{"tree":{"sha":TREE}},ROOT+"/git/trees/"+TREE+"?recursive=1":{"truncated":False,"tree":[{"type":"blob","path":str(i),"sha":f"{i:040x}"[-40:]} for i in range(100)]}}; raw={}
 for k,(wid,name,job,art,member,steps) in WORKFLOWS.items():
  rid=100+wid; raw[rid]=z(k,member); v[ROOT+f"/actions/workflows/{wid}/runs?event=pull_request&status=success&per_page=100"]={"workflow_runs":[{"id":rid,"name":name,"event":"pull_request","status":"completed","conclusion":"success","run_attempt":1,"head_sha":SHA}]}; v[ROOT+f"/actions/runs/{rid}/jobs?per_page=100"]={"total_count":1,"jobs":[{"name":job,"run_id":rid,"head_sha":SHA,"status":"completed","conclusion":"success","steps":[{"name":x,"status":"completed","conclusion":"success"} for x in steps]}]}; v[ROOT+f"/actions/runs/{rid}/artifacts?per_page=100"]={"total_count":1,"artifacts":[{"id":rid,"name":art,"expired":False,"digest":"sha256:"+hashlib.sha256(raw[rid]).hexdigest(),"size_in_bytes":len(raw[rid]),"archive_download_url":f"https://api.github.com/repos/{REPO}/actions/artifacts/{rid}/zip","workflow_run":{"id":rid,"head_sha":SHA,"head_repository_id":1387883686}}]}
 for path in TRUSTED_SCANNER_FILES:v[ROOT+"/contents/"+path+"?ref="+TRUSTED_SCANNER_SHA]={"sha":"e"*40,"size":1};v[ROOT+"/contents/"+path+"?ref="+SHA]={"sha":"e"*40,"size":1}
 return v,raw
class TestSecurityEvidence(unittest.TestCase):
 def proof(self,v=None,r=None):
  v,r=fixture() if v is None else (v,r);return verify_existing_secrets_dependencies(repository=REPO,assessed_commit=SHA,github_get=lambda p:v[p],archive_fetch=lambda u,t,i:r[i],environment=env())
 def test_tree_bound_scans_pass(self):self.assertEqual(self.proof().retained_receipt["tree_oid"],TREE)
 def test_outside_tree_drift_blocks(self):
  v,r=fixture();v[ROOT+"/git/commits/"+SHA]={"tree":{"sha":"c"*40}};v[ROOT+"/git/trees/"+("c"*40)+"?recursive=1"]=v[ROOT+"/git/trees/"+TREE+"?recursive=1"]
  with self.assertRaises(SecurityEvidenceBlocked):self.proof(v,r)
 def test_digest_job_and_receipt_forgery_block(self):
  for x in ("digest","job","receipt"):
   v,r=fixture();wid=WORKFLOWS["gitleaks"][0];rid=100+wid
   if x=="digest":v[ROOT+f"/actions/runs/{rid}/artifacts?per_page=100"]["artifacts"][0]["digest"]="sha256:"+"0"*64
   elif x=="job":v[ROOT+f"/actions/runs/{rid}/jobs?per_page=100"]["jobs"][0]["name"]="wrong"
   else:
    b=receipt("gitleaks");b["tree_oid"]="d"*40;o=io.BytesIO()
    with zipfile.ZipFile(o,"w") as a:a.writestr(WORKFLOWS["gitleaks"][4],json.dumps(b))
    r[rid]=o.getvalue();q=v[ROOT+f"/actions/runs/{rid}/artifacts?per_page=100"]["artifacts"][0];q["digest"]="sha256:"+hashlib.sha256(r[rid]).hexdigest();q["size_in_bytes"]=len(r[rid])
   with self.subTest(x=x),self.assertRaises(SecurityEvidenceBlocked):self.proof(v,r)
 def test_scanner_source_drift_blocks(self):
  for path in TRUSTED_SCANNER_FILES:
   with self.subTest(path=path):
    v,r=fixture();v[ROOT+"/contents/"+path+"?ref="+SHA]["sha"]="f"*40
    with self.assertRaises(SecurityEvidenceBlocked):self.proof(v,r)
 def test_credential_exposure_receipt_blocks_pass(self):
  v,r=fixture();wid=WORKFLOWS["gitleaks"][0];rid=100+wid;b=receipt("gitleaks");o=io.BytesIO()
  with zipfile.ZipFile(o,"w") as a:
   a.writestr(WORKFLOWS["gitleaks"][4],json.dumps(b));a.writestr("block1-credential-exposure-receipt.json",json.dumps({"schema":"factory-block1-credential-exposure-v4","scope":"static-import-reachability-for-client-public-health-and-per-http-handler-guards-not-runtime-authentication","console_files_scanned":1,"client_entrypoints_scanned":1,"route_handlers_scanned":1,"public_surface_roots":["apps/console/app/api/health/route.ts"],"credential_exposure_detected":True,"privileged_values_read":False,"security_certified":False,"writes":0,"paid_calls":0,"findings":[{"path":"x"}]}))
  r[rid]=o.getvalue();artifact=v[ROOT+f"/actions/runs/{rid}/artifacts?per_page=100"]["artifacts"][0];artifact["digest"]="sha256:"+hashlib.sha256(r[rid]).hexdigest();artifact["size_in_bytes"]=len(r[rid])
  with self.assertRaises(SecurityEvidenceBlocked):self.proof(v,r)

 def test_merge_parent_restricts_scanner_to_human_merged_candidate(self):
   from ai_product_factory.independent_security_evidence import _scan_run
   v,raw=fixture()
   candidate="c"*40
   v[ROOT+"/git/commits/"+SHA]["parents"]=[
     {"sha":"d"*40},{"sha":candidate}]
   v[ROOT+"/git/commits/"+candidate]={"tree":{"sha":TREE}}
   for kind,(wid,name,job,art,member,steps) in WORKFLOWS.items():
     runlist=v[ROOT+f"/actions/workflows/{wid}/runs?event=pull_request&status=success&per_page=100"]["workflow_runs"]
     original=runlist[0]
     original["head_sha"]=candidate
     v[ROOT+f"/actions/runs/{original['id']}/jobs?per_page=100"]["jobs"][0]["head_sha"]=candidate
     # An unrelated successful scan, even of an identical Git tree, must
     # never be promoted to merge-provenance. The endpoint for its SHA is
     # deliberately absent; querying it indicates the old 100-tree scan.
     runlist.insert(0,{**original,"id":987654321,"head_sha":"e"*40})
     seen=[]
     def get(path):
       seen.append(path)
       return v[path]
     row,rid=_scan_run(get,ROOT,kind,TREE,SHA)
     self.assertEqual(row["head_sha"],candidate)
     self.assertEqual(rid,original["id"])
     self.assertEqual([p for p in seen if "/git/trees/" in p],
                      [ROOT+"/git/trees/"+TREE+"?recursive=1"])
     self.assertFalse(any("/git/commits/"+("e"*40) in p for p in seen))
     # Candidate source and exact tree must both be verified.
     runlist[:]=[runlist[0]]
     with self.assertRaises(SecurityEvidenceBlocked):
       _scan_run(lambda path:v[path],ROOT,kind,TREE,SHA)
     runlist[:]=[original]
     v[ROOT+"/git/commits/"+candidate]={"tree":{"sha":"f"*40}}
     v[ROOT+"/git/trees/"+("f"*40)+"?recursive=1"]=v[ROOT+"/git/trees/"+TREE+"?recursive=1"]
     with self.assertRaises(SecurityEvidenceBlocked):
       _scan_run(lambda path:v[path],ROOT,kind,TREE,SHA)
     v[ROOT+"/git/commits/"+candidate]={"tree":{"sha":TREE}}
     runlist.append(dict(original,id=77777777))
     duplicate_job=copy.deepcopy(v[ROOT+f"/actions/runs/{original['id']}/jobs?per_page=100"])
     duplicate_job["jobs"][0]["run_id"]=77777777
     v[ROOT+"/actions/runs/77777777/jobs?per_page=100"]=duplicate_job
     # Two successful scans of the SAME immutable second parent are genuine
     # duplicate executions, not two ambiguous source revisions.
     chosen,rid=_scan_run(lambda path:v[path],ROOT,kind,TREE,SHA)
     self.assertEqual(rid,77777777)
     self.assertEqual(chosen["head_sha"],candidate)
     v[ROOT+"/actions/runs/77777777/jobs?per_page=100"]["jobs"][0]["conclusion"]="failure"
     with self.assertRaises(SecurityEvidenceBlocked):
       _scan_run(lambda path:v[path],ROOT,kind,TREE,SHA)
     v[ROOT+"/actions/runs/77777777/jobs?per_page=100"]["jobs"][0]["conclusion"]="success"
     runlist.append(dict(original,id=77777777))
     with self.assertRaises(SecurityEvidenceBlocked):
       _scan_run(lambda path:v[path],ROOT,kind,TREE,SHA)

 def test_invalid_merge_parent_never_falls_back_to_same_tree(self):
   from ai_product_factory.independent_security_evidence import _scan_run
   for parents in ([],[{"sha":"not-a-sha"}],[{"sha":"c"*40},{"sha":"c"*40}],
                   [{"sha":"a"*40},{"sha":"d"*40},{"sha":"e"*40}],"invalid"):
     v,_=fixture()
     v[ROOT+"/git/commits/"+SHA]["parents"]=parents
     with self.subTest(parents=parents), self.assertRaises(SecurityEvidenceBlocked):
       _scan_run(lambda path:v[path],ROOT,"gitleaks",TREE,SHA)
