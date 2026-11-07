"""W-DATA-01-A: testes exclusivamente offline, fakes sem gh/API/mutations reais."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/ch_project_autonomy.py"
spec = importlib.util.spec_from_file_location("ch_project_autonomy", SCRIPT)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


def context():
    items = []
    for n in app.ISSUES:
        items.append({
            "id": f"PVTI_{n}",
            "status": "Todo", "Etapa CH": "AGUARDANDO_PO" if n == 24 else "INTEGRADA",
            "Esteira": "Hallan" if n == 10 else "ChatGPT",
            "Prioridade CH": None, "Risco CH": None, "Decisao PO": None,
            "content": {"number": n, "type": "Issue", "repository": app.REPO,
                        "url": f"https://github.com/{app.REPO}/issues/{n}"},
        })
    return {
        "project": {"id": "PVT_project2"},
        "fields": {"fields": [{"name": app.FIELD, "type": "ProjectV2SingleSelectField",
                              "id": "field_AUTONOMIA", "options": [
                                  {"name": "CH-0", "id": "opt0"},
                                  {"name": "CH-1", "id": "opt1"}]}]},
        "items": {"items": items, "totalCount": len(items)},
    }


def ch1_plan(ctx):
    rows=[]
    for n, item in zip(app.ISSUES, ctx["items"]["items"]):
        rows.append({"issue":n,"card_id":item["id"],"issue_url":item["content"]["url"],
                     "field":app.FIELD,"field_id":"field_AUTONOMIA",
                     "before":"NÃO_OBSERVADO","proposed_after":app.TARGETS[n],
                     "option_id":"opt1" if app.TARGETS[n]=="CH-1" else "opt0",
                     "preserve":{"Etapa CH":item["Etapa CH"],"Esteira":item["Esteira"]}})
    p={"schema":app.CH1_SCHEMA,"read_only":True,"not_an_apply_plan":True,
       "authorized_phase":"CH-1","repo":app.REPO,"project":app.PROJECT,
       "source":"LIVE_GITHUB","source_snapshot_sha256":app.SNAPSHOT_DIGEST,
       "issues":list(app.ISSUES),"changes":rows,
       "po_ratification":{"issue":10,"to_proposal":"CH-1","write_authorized":False}}
    p["digest_sha256"]=app.digest(p)
    return p


def make_plan(ctx=None):
    ctx=ctx or context()
    # O digest real do CH-1 é protegido; o fixture é gerado no teste.
    fake_ch1=ch1_plan(ctx)
    with patch.object(app,"CH1_DIGEST",fake_ch1["digest_sha256"]):
        p=app.make_apply_plan(fake_ch1,ctx)
    p["source_ch1_digest_sha256"]=app.CH1_DIGEST
    p["digest_sha256"]=app.digest(app.unsigned(p))
    return p


def approval(plan, comment_id=321):
    return {"id":comment_id,"issue_url":f"https://api.github.com/repos/{app.REPO}/issues/62",
            "user":{"login":app.OWNER},"created_at":"2026-11-07T18:00:00Z",
            "updated_at":"2026-11-07T18:00:00Z",
            "body":app.approval_statement(plan["digest_sha256"])+"\n"
                  +"ACEITO RISCO RESIDUAL DE CONCORRENCIA SEM CAS ATOMICO"}


class Fake:
    def __init__(self, p):
        self.plan=p
        self.live=context()
        self.proof=approval(p)
        self.events=[]
        self.mutations=[]
        self.reader_calls=0
        self.fail_at=None
        self.fail_after_mutation=False

    def reader(self):
        self.reader_calls += 1
        return copy.deepcopy(self.live)

    def writer(self, args):
        self.mutations.append(copy.deepcopy(args))
        idx=len(self.mutations)
        if self.fail_at==idx and not self.fail_after_mutation:
            raise TimeoutError("mock timeout antes da mutation")
        match=next(i for i in self.live["items"]["items"] if i["id"]==args["itemId"])
        value={"opt0":"CH-0","opt1":"CH-1"}[args["optionId"]]
        match[app.FIELD]=value
        if self.fail_at==idx and self.fail_after_mutation:
            raise TimeoutError("mock timeout após a mutation")
        return args["itemId"]

    def run(self, *, interactive=True, response=True, audit=None):
        return app.apply_plan(self.plan,321,reader=self.reader,proof_reader=lambda _:self.proof,
                              graphql_set=self.writer,audit=self.events.append if audit is None else audit,
                              interactive=interactive,prompt=lambda _: "APROVO CH-DATA-01 " + self.plan["digest_sha256"][:12] if response else "NAO")


class Contract(unittest.TestCase):
    def setUp(self):
        self.c=context()
        self.p=make_plan(self.c)

    def sign(self, p):
        p["digest_sha256"]=app.digest(app.unsigned(p))
        return p

    def test_schema_rejects_ch1_as_applicable(self):
        with self.assertRaises(ValueError):
            app.validate_apply_plan(ch1_plan(self.c))

    def test_dry_run_requires_no_remote_calls(self):
        fake_ch1=ch1_plan(self.c)
        with patch.object(app,"CH1_DIGEST",fake_ch1["digest_sha256"]), patch.object(app,"live_reader") as live:
            with tempfile.TemporaryDirectory() as td:
                path=Path(td)/"ch1.json"
                path.write_text(json.dumps(fake_ch1))
                self.assertEqual(app.main(["--ch1-plan",str(path)]),0)
            live.assert_not_called()

    def test_digest_tampered(self):
        self.p["changes"][0]["after"]="CH-2"
        with self.assertRaisesRegex(ValueError,"Digest"):
            app.validate_apply_plan(self.p)

    def test_digest_resigned_wrong_target(self):
        self.sign(self.p)
        self.p["changes"][0]["after"]="CH-2"
        self.sign(self.p)
        with self.assertRaisesRegex(ValueError,"allowlist"):
            app.validate_apply_plan(self.p)

    def test_wrong_item_issue_and_option_ids(self):
        for field,value in [("card_id","PVTI_fake"),("option_id","")]:
            with self.subTest(field=field):
                p=copy.deepcopy(self.p);p["changes"][1][field]=value;self.sign(p)
                if field=="card_id":
                    with self.assertRaises(ValueError): app.check_live(p,self.c,set())
                else:
                    with self.assertRaises(ValueError): app.validate_apply_plan(p)

    def test_wrong_issue_url(self):
        self.p["changes"][2]["issue_url"]="https://evil.example.com"
        self.sign(self.p)
        with self.assertRaises(ValueError): app.validate_apply_plan(self.p)

    def test_optional_mutation_fields_rejected(self):
        self.p["changes"][0]["another_field"]="Etapa CH"
        self.sign(self.p)
        with self.assertRaises(ValueError): app.validate_apply_plan(self.p)

    def test_before_not_null_rejected(self):
        self.p["changes"][0]["before"]="CH-2";self.sign(self.p)
        with self.assertRaises(ValueError): app.validate_apply_plan(self.p)

    def test_duplicate_missing_lot_items(self):
        self.c["items"]["items"][1]["content"]["number"]=8
        with self.assertRaises(ValueError): app.check_live(self.p,self.c,set())

    def test_changed_other_field_fails(self):
        for field,value in [("Etapa CH","HOMOLOGADA"),("Esteira","AGY"),
                            ("Decisao PO","APROVADO"),("Risco CH","ALTO"),
                            ("Prioridade CH","P0"),("status","Done")]:
            with self.subTest(field=field):
                c=copy.deepcopy(self.c);c["items"]["items"][0][field]=value
                with self.assertRaises(ValueError): app.check_live(self.p,c,set())

    def test_existing_autonomy_blocks(self):
        self.c["items"]["items"][0][app.FIELD]="CH-0"
        with self.assertRaises(ValueError): app.check_live(self.p,self.c,set())

    def test_live_options_mismatch(self):
        self.c["fields"]["fields"][0]["options"][0]["id"]="changed"
        with self.assertRaises(ValueError): app.check_live(self.p,self.c,set())

    def test_live_project_wrong(self):
        self.c["project"]["id"]="wrong"
        with self.assertRaises(ValueError): app.check_live(self.p,self.c,set())

    def test_stale_plan_rejected(self):
        p=copy.deepcopy(self.p)
        p["prepared_at_utc"]=(datetime.now(timezone.utc)-timedelta(days=3)).isoformat()
        self.sign(p)
        with self.assertRaisesRegex(ValueError,"expirou"):
            app.validate_apply_plan(p)

    def test_auth_wrong_author_and_issue(self):
        a=approval(self.p)
        a["user"]["login"]="outsider"
        with self.assertRaises(ValueError): app.verify_approval(a,self.p,321)
        a=approval(self.p)
        a["issue_url"]="https://api.github.com/repos/hallanbrito/CHDevFlow/issues/8"
        with self.assertRaises(ValueError): app.verify_approval(a,self.p,321)

    def test_auth_wrong_values_missing_risk(self):
        a=approval(self.p);a["body"]=a["body"].replace("#10=CH-1","#10=CH-0")
        with self.assertRaises(ValueError):app.verify_approval(a,self.p,321)
        a=approval(self.p);a["body"]=a["body"].splitlines()[0]
        with self.assertRaises(ValueError):app.verify_approval(a,self.p,321)

    def test_no_tty_and_confirmation(self):
        f=Fake(self.p)
        with self.assertRaises(ValueError):f.run(interactive=False)
        self.assertEqual(f.mutations,[])
        f=Fake(self.p)
        with self.assertRaises(RuntimeError):f.run(response=False)
        self.assertEqual(f.mutations,[])

    def test_success_exactly_five_set_calls_and_readback(self):
        f=Fake(self.p)
        self.assertEqual(f.run(),5)
        self.assertEqual(len(f.mutations),5)
        self.assertTrue(all(set(m)=={"projectId","itemId","fieldId","optionId"} for m in f.mutations))
        self.assertGreaterEqual(f.reader_calls,11)
        self.assertEqual([e["event"] for e in f.events].count("VERIFIED"),5)
        self.assertEqual(f.events[-1]["event"],"COMPLETE")

    def test_timeout_before_and_after_write_no_retry(self):
        for after in (False,True):
            f=Fake(self.p);f.fail_at=3;f.fail_after_mutation=after
            with self.subTest(after=after),self.assertRaisesRegex(RuntimeError,"incerta=#12"):
                f.run()
            self.assertEqual(len(f.mutations),3)
            self.assertEqual(f.events[-1]["event"],"UNCERTAIN")
            self.assertEqual(f.events[-1]["confirmed"],[8,10])

    def test_partial_rerun_blocks(self):
        f=Fake(self.p);f.fail_at=3
        with self.assertRaises(RuntimeError):f.run()
        with self.assertRaises(RuntimeError):f.run()
        self.assertEqual(len(f.mutations),3)

    def test_success_then_other_fields_changed_blocks(self):
        f=Fake(self.p)
        original=f.writer
        def dangerous(args):
            z=original(args)
            if len(f.mutations)==1:
                f.live["items"]["items"][2]["Esteira"]="AGY"
            return z
        f.writer=dangerous
        with self.assertRaises(RuntimeError):f.run()
        self.assertEqual(len(f.mutations),1)
        self.assertEqual(f.events[-1]["event"],"UNCERTAIN")

    def test_changed_po_comment_during_run(self):
        f=Fake(self.p);original=f.writer
        def edit_comment(args):
            ret=original(args)
            f.proof["updated_at"]="2099-01-01T00:00:00Z"
            return ret
        f.writer=edit_comment
        with self.assertRaises(RuntimeError): f.run()
        self.assertEqual(len(f.mutations),1)

    def test_audit_failure_blocks_further_mutations(self):
        f=Fake(self.p)
        def audit(event):
            if event["event"]=="ATTEMPT":
                raise OSError("disk full")
            f.events.append(event)
        with self.assertRaises(RuntimeError):f.run(audit=audit)
        self.assertEqual(len(f.mutations),0)

    def test_exclusive_jsonl_and_permissions(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"audit.jsonl"
            with app._audit_open(path) as fh:
                app._audit_record(fh,"abc")({"event":"PREFLIGHT"})
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertEqual(json.loads(path.read_text().strip())["event"],"PREFLIGHT")
            with self.assertRaises(FileExistsError):app._audit_open(path)

    def test_set_only_has_no_add_operation(self):
        with patch.object(app,"_module") as module:
            module.return_value._admit_graphql.return_value="PVTI_8"
            self.assertEqual(app.set_only({"projectId":"p","itemId":"i","fieldId":"f","optionId":"o"}),"PVTI_8")
            module.return_value._admit_graphql.assert_called_once_with("set",{"projectId":"p","itemId":"i","fieldId":"f","optionId":"o"})
        with self.assertRaises(ValueError): app.set_only({"operation":"add"})


if __name__ == "__main__":
    unittest.main()