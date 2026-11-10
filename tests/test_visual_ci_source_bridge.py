import unittest
from ai_product_factory.visual_ci_source_bridge import (
    bind_exact_ci_source,VisualCIBindingBlocked,REPOSITORY,VISUAL,VISUAL_PATH,
)
SHA="a"*40
RID=10002
VID=10003
P="/repos/"+REPOSITORY
def fixture():
    visual=dict(id=VID,name=VISUAL,path=VISUAL_PATH,event="workflow_dispatch",
        head_sha=SHA,head_branch="main",run_attempt=1,status="completed",
        conclusion="success",repository={"full_name":REPOSITORY})
    validate=dict(id=RID,name="validate",path=".github/workflows/validate.yml",
        event="push",head_sha=SHA,head_branch="main",run_attempt=1,
        status="completed",conclusion="success",repository={"full_name":REPOSITORY})
    data={
      P+"/actions/runs/"+str(VID):dict(visual),
      P+"/actions/runs/"+str(RID):validate,
      P+"/actions/runs/"+str(RID)+"/jobs?per_page=100":{
          "total_count":2,"jobs":[
              {"run_id":RID,"head_sha":SHA,"status":"completed","conclusion":"success","name":"test"},
              {"run_id":RID,"head_sha":SHA,"status":"completed","conclusion":"success","name":"factory-acceptance"},
          ]},
      P+"/git/ref/heads/main":{"object":{"sha":SHA}}
    }
    return visual,data
def resolve(visual=None,data=None):
    v,d=fixture()
    return bind_exact_ci_source(repository=REPOSITORY,assessed_commit=SHA,
       actual_event={"workflow_run":v if visual is None else visual},
       validation_run_id=RID,github_get=(lambda p:(d if data is None else data)[p]))
class ExactCIVisualBridgeTests(unittest.TestCase):
    def test_visual_success_derives_real_exact_sha_validation(self):
        result=resolve()
        self.assertEqual(result["workflow_run"]["id"],RID)
        self.assertEqual(result["workflow_run"]["name"],"validate")
    def test_first_attempt_post_merge_push_visual_derives_real_exact_sha_validation(self):
        visual, data = fixture()
        visual["event"] = "push"
        data[P+"/actions/runs/"+str(VID)]["event"] = "push"
        result = resolve(visual, data)
        self.assertEqual(result["workflow_run"]["id"], RID)
        for changes in ({"run_attempt": 2}, {"head_sha": "b"*40}, {"conclusion": "failure"}):
            with self.subTest(changes=changes), self.assertRaises(VisualCIBindingBlocked):
                resolve({**visual,**changes}, data)

    def test_validate_event_never_substituted(self):
        visual,_=fixture()
        self.assertIsNone(resolve({**visual,"name":"validate"}))
    def test_mutated_or_failed_visual_denied(self):
        visual,_=fixture()
        for changes in [{"conclusion":"failure"},{"run_attempt":2},{"head_sha":"b"*40},
                        {"event":"push"},{"path":"fake"},{"id":-1}]:
            with self.subTest(changes=changes),self.assertRaises(VisualCIBindingBlocked):
                resolve({**visual,**changes})
    def test_untrusted_git_provenance_denied(self):
        visual,data=fixture()
        for path,key,value in [
            (P+"/actions/runs/"+str(RID),"conclusion","failure"),
            (P+"/actions/runs/"+str(RID),"head_sha","b"*40),
            (P+"/actions/runs/"+str(VID),"status","in_progress"),
        ]:
            fake={k:dict(v) for k,v in data.items()}
            fake[path]={**fake[path],key:value}
            with self.subTest(path=path,key=key),self.assertRaises(VisualCIBindingBlocked):
                resolve(visual,fake)
    def test_main_movement_or_missing_jobs_denied(self):
        visual,data=fixture()
        bad={**data,P+"/git/ref/heads/main":{"object":{"sha":"b"*40}}}
        with self.assertRaises(VisualCIBindingBlocked):resolve(visual,bad)
        broken={**data,P+"/actions/runs/"+str(RID)+"/jobs?per_page=100":{"total_count":1,"jobs":[data[P+"/actions/runs/"+str(RID)+"/jobs?per_page=100"]["jobs"][0]]}}
        with self.assertRaises(VisualCIBindingBlocked):resolve(visual,broken)
if __name__=="__main__":unittest.main()
