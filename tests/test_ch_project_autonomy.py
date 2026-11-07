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



def r1_evidence():
    shared = {"protocol": "RUC/1.0", "mission": "W-DATA-01-A",
              "plan_sha256": app.R1_APPLY_DIGEST, "timestamp_utc": "2026-11-07T18:22:26Z"}
    detail = [
        {"event": "PREFLIGHT"}, {"event": "AUTH_VERIFIED"},
        {"event": "START", "issues": list(app.ISSUES)},
        {"event": "ATTEMPT", "issue": 8, "field": app.FIELD, "before": None,
         "after_expected": "CH-1", "card_id": "PVTI_8"},
        {"event": "VERIFIED", "issue": 8, "field": app.FIELD, "after": "CH-1",
         "card_id": "PVTI_8"},
        {"event": "ABORT", "confirmed": [8], "uncertain_issue": None}
    ]
    return [{**shared, **x} for x in detail]


def r2_context():
    c = context()
    c["items"]["items"][0][app.FIELD] = "CH-1"
    return c


def r2_plan(c=None):
    c = c or r2_context()
    ch1 = ch1_plan(context())
    with patch.object(app, "CH1_DIGEST", ch1["digest_sha256"]):
        p = app.make_resume_plan(ch1, c, r1_evidence(), "a" * 64)
    p["source_ch1_digest_sha256"] = app.CH1_DIGEST
    p["digest_sha256"] = app.digest(app.unsigned(p))
    return p


def r2_approval(p, comment_id=987):
    return {"id": comment_id, "user": {"login": app.OWNER},
            "issue_url": f"https://api.github.com/repos/{app.REPO}/issues/62",
            "created_at": "2026-11-07T19:00:00Z",
            "updated_at": "2026-11-07T19:00:00Z",
            "body": app.resume_approval_statement(p["digest_sha256"]) + "\n"
                    + "ACEITO RISCO RESIDUAL DE CONCORRENCIA SEM CAS ATOMICO"}


class R2Contract(unittest.TestCase):
    """Todos os cenários são fakes offline; não chamam gh nem GraphQL real."""

    def setUp(self):
        self.c = r2_context()
        self.p = r2_plan(self.c)

    def sign(self, p):
        p["digest_sha256"] = app.digest(app.unsigned(p))
        return p

    def execute(self, *, c=None, consent=True, permission=True, error_at=None,
                after_write=False, audit=None):
        c = copy.deepcopy(c or self.c)
        proof = r2_approval(self.p)
        calls = {"schema": 0, "items": 0, "writes": []}
        events = []
        def schema():
            calls["schema"] += 1
            return copy.deepcopy(c)
        def items():
            calls["items"] += 1
            if error_at == "quota" and calls["items"] == 3:
                raise RuntimeError("GraphQL API rate limit")
            return copy.deepcopy(c["items"])
        def write(data):
            calls["writes"].append(copy.deepcopy(data))
            if error_at == len(calls["writes"]) and not after_write:
                raise TimeoutError("mock pre-write timeout")
            item = next(x for x in c["items"]["items"] if x["id"] == data["itemId"])
            item[app.FIELD] = {"opt0": "CH-0", "opt1": "CH-1"}[data["optionId"]]
            if error_at == len(calls["writes"]) and after_write:
                raise TimeoutError("mock post-write timeout")
            return data["itemId"]
        def start():
            return app.apply_resume_plan(
                self.p, 987, schema_reader=schema, items_reader=items,
                proof_reader=lambda _: proof, graphql_set=write,
                audit=audit or events.append, interactive=permission,
                prompt=lambda _: ("APROVO CH-DATA-01 R2 " + self.p["digest_sha256"][:12])
                      if consent else "NAO")
        return start, calls, events, c, proof

    def test_only_four_changes_and_eight_is_precondition(self):
        self.assertEqual(self.p["issues"], [10, 12, 13, 24])
        self.assertEqual(self.p["precondition"]["issue"], 8)
        self.assertEqual(self.p["precondition"]["before"], "CH-1")
        self.assertEqual([x["after"] for x in self.p["changes"]],
                         ["CH-1", "CH-0", "CH-0", "CH-1"])
        self.assertEqual(len(app.validate_resume_plan(self.p)), 4)
        with self.assertRaises(ValueError):
            app.validate_apply_plan(self.p)

    def test_eight_missing_or_wrong_value_blocks(self):
        for wrong in (None, "CH-0"):
            c = copy.deepcopy(self.c)
            c["items"]["items"][0][app.FIELD] = wrong
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                app.check_resume_live(self.p, c, set())
            with patch.object(app, "CH1_DIGEST", ch1_plan(context())["digest_sha256"]):
                with self.assertRaises(ValueError):
                    app.make_resume_plan(ch1_plan(context()), c, r1_evidence(), "a" * 64)

    def test_no_overwrite_of_existing_pending(self):
        c = copy.deepcopy(self.c)
        c["items"]["items"][1][app.FIELD] = "CH-1"
        with self.assertRaises(ValueError): app.check_resume_live(self.p, c, set())

    def test_protected_fields_and_ids_fail_closed(self):
        for key, val in [("Etapa CH", "HOMOLOGADA"), ("Esteira", "AGY"),
                         ("Prioridade CH", "P0"), ("status", "Done")]:
            c = copy.deepcopy(self.c)
            c["items"]["items"][0][key] = val
            with self.subTest(key=key), self.assertRaises(ValueError):
                app.check_resume_live(self.p, c, set())
        c = copy.deepcopy(self.c)
        c["items"]["items"][1]["id"] = "PVTI_X"
        with self.assertRaises(ValueError): app.check_resume_live(self.p, c, set())

    def test_digest_and_scope_cannot_be_forged(self):
        for key, val in [("source_r1_plan_sha256", "0"*64),
                         ("issues", [8, 10, 12, 13, 24]),
                         ("source_ch1_digest_sha256", "0"*64)]:
            p = copy.deepcopy(self.p)
            p[key] = val
            self.sign(p)
            with self.subTest(key=key), self.assertRaises(ValueError):
                app.validate_resume_plan(p)
        p = copy.deepcopy(self.p)
        p["changes"][0]["after"] = "CH-2"
        with self.assertRaises(ValueError): app.validate_resume_plan(p)

    def test_r1_audit_exact_sequence_and_sha(self):
        import hashlib
        ev = r1_evidence()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"r1.jsonl"
            p.write_text("".join(json.dumps(x) + "\n" for x in ev))
            got, sha = app.read_r1_audit(p)
            self.assertEqual(got, ev)
            self.assertEqual(sha, hashlib.sha256(p.read_bytes()).hexdigest())
            ev[3]["issue"] = 10
            p.write_text("".join(json.dumps(x) + "\n" for x in ev))
            with self.assertRaises(ValueError): app.read_r1_audit(p)

    def test_success_four_mutations_and_schema_cache(self):
        run, call, events, c, _ = self.execute()
        self.assertEqual(run(), 4)
        self.assertEqual(call["schema"], 2)
        self.assertEqual(call["items"], 8)
        self.assertEqual([x["itemId"] for x in call["writes"]],
                         ["PVTI_10", "PVTI_12", "PVTI_13", "PVTI_24"])
        self.assertEqual(c["items"]["items"][0][app.FIELD], "CH-1")
        self.assertEqual(sum(e["event"] == "VERIFIED_R2" for e in events), 4)
        self.assertEqual(events[-1]["event"], "COMPLETE_R2")

    def test_tty_and_human_confirmation_no_writes(self):
        for kwargs in [{"permission": False}, {"consent": False}]:
            run, calls, _, _, _ = self.execute(**kwargs)
            with self.assertRaises((RuntimeError, ValueError)): run()
            self.assertEqual(calls["writes"], [])

    def test_new_approval_author_and_risk_required(self):
        proof = r2_approval(self.p)
        self.assertTrue(app.verify_resume_approval(proof, self.p, 987))
        proof["user"]["login"] = "intruso"
        with self.assertRaises(ValueError):
            app.verify_resume_approval(proof, self.p, 987)
        proof = r2_approval(self.p)
        proof["body"] = proof["body"].splitlines()[0]
        with self.assertRaises(ValueError):
            app.verify_resume_approval(proof, self.p, 987)

    def test_graphql_quota_after_first_verified_stops_no_retry(self):
        run, calls, events, _, _ = self.execute(error_at="quota")
        with self.assertRaisesRegex(RuntimeError, "1 verificadas"): run()
        self.assertEqual(len(calls["writes"]), 1)
        self.assertEqual(events[-1]["event"], "ABORT_R2")

    def test_timeout_before_after_write_is_uncertain(self):
        for after in (False, True):
            run, calls, events, _, _ = self.execute(error_at=2, after_write=after)
            with self.subTest(after=after), self.assertRaisesRegex(RuntimeError, "incerta=#12"):
                run()
            self.assertEqual(len(calls["writes"]), 2)
            self.assertEqual(events[-1]["event"], "UNCERTAIN_R2")

    def test_audit_failure_prevents_mutation(self):
        def audit(event):
            if event["event"] == "ATTEMPT_R2":
                raise OSError("mock disk full")
        run, calls, _, _, _ = self.execute(audit=audit)
        with self.assertRaises(RuntimeError): run()
        self.assertEqual(calls["writes"], [])


if __name__ == "__main__":
    unittest.main()