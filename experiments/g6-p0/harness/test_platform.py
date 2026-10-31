"""纯合成 Provider/预算/资源合同正反验收，无 API、Secret 或 Docker 操作。"""
import contextlib
import copy
from datetime import datetime, timedelta, timezone
from fractions import Fraction
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from platform_contract import (ContractError, Budget, validate_provider, validate_deployment,
    validate_profile, authorize_route, safe_record, cleanup_eligible, validate_compose)

ROOT = Path(__file__).resolve().parents[1]


class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((ROOT / "design/provider-catalog.json").read_text())
        self.provider = copy.deepcopy(self.catalog["providers"][0])
        self.policy = copy.deepcopy(self.catalog["policies"][0])
        self.provider["enabled"] = True
        self.policy["approved"] = True
        self.deployment = copy.deepcopy(self.catalog["deployments"][0])
        self.profile = copy.deepcopy(self.catalog["profiles"][0])
        self.cost = dict(maxRequests=2, maxInputTokens=20, maxOutputTokens=20,
            maxCostUsd="0.10", maxSeconds=10, maxRetries=1, maxConcurrency=1,
            inputUsdPerToken="0.001", outputUsdPerToken="0.002",
            priceSnapshot="synthetic-price-v1", currency="USD")

    def test_bad_endpoint_forms(self):
        for url in ["http://api.openai.com/v1", "https://api.openai.com.evil.test/v1",
                    "https://u:p@api.openai.com/v1", "https://api.openai.com/v1?key=fake",
                    "https://127.0.0.1/v1", "https://169.254.169.254/v1",
                    "https://api.openai.com/v1#secret", "https://api.openai.com:444/v1"]:
            with self.subTest(url=url):
                self.provider["baseUrl"] = url
                with self.assertRaises(ContractError): validate_provider(self.provider, self.policy)

    def test_secret_cross_scope_rejected(self):
        self.provider["secretRef"]["tenantScope"] = "other"
        with self.assertRaises(ContractError): validate_provider(self.provider, self.policy)

    def test_secret_wrong_provider_rejected(self):
        self.provider["secretRef"]["providerId"] = "other"
        with self.assertRaises(ContractError): validate_provider(self.provider, self.policy)

    def test_secret_path_and_unknown_rejected(self):
        for path in ["/run/secrets/../key", "/tmp/key", "/run/secrets/key/child"]:
            self.provider["secretRef"]["mountPath"] = path
            with self.assertRaises(ContractError): validate_provider(self.provider, self.policy)
        self.provider = copy.deepcopy(self.catalog["providers"][0])
        self.provider["apiKey"] = "MOCK" + "_SECRET"
        with self.assertRaises(ContractError): validate_provider(self.provider, self.policy)

    def test_provider_bool_revision_rejected(self):
        self.provider["revision"] = True
        with self.assertRaises(ContractError): validate_provider(self.provider, self.policy)

    def test_provider_policy_binding_rejected(self):
        self.policy["tenantScope"] = "other"
        with self.assertRaises(ContractError): validate_provider(self.provider, self.policy)

    def test_six_presets_disabled_valid(self):
        self.assertEqual({p["providerType"] for p in self.catalog["providers"]},
                         {"openai", "deepseek", "qwen", "glm", "kimi", "ollama"})
        for p, policy in zip(self.catalog["providers"], self.catalog["policies"]):
            validate_provider(p, policy)
            self.assertFalse(p["enabled"])
            self.assertFalse(policy["approved"])

    def test_ollama_requires_local_policy(self):
        p, policy = copy.deepcopy(self.catalog["providers"][-1]), copy.deepcopy(self.catalog["policies"][-1])
        policy["allowLocal"] = False
        with self.assertRaises(ContractError): validate_provider(p, policy)

    def test_unknown_capability_not_ready(self):
        self.deployment["authentication"] = "PASS"
        validate_deployment(self.deployment)
        with self.assertRaises(ContractError):
            authorize_route(self.profile, self.provider, self.deployment, self.policy, "SYNTHETIC", "jsonSchema")

    def ready(self):
        self.deployment["authentication"] = "PASS"
        self.deployment["capabilities"]["jsonSchema"] = "PASS"
        self.deployment["probe"] = dict(providerId=self.provider["providerId"],
            deploymentId=self.deployment["deploymentId"], modelId=self.deployment["modelId"],
            registrySnapshot=self.deployment["registrySnapshot"], schemaHash="a"*64,
            sampleVersion="synthetic-v1", probeVersion=1, capability="jsonSchema", status="PASS")

    def test_probe_mismatched_model_rejected(self):
        self.ready(); self.deployment["probe"]["modelId"] = "different"
        with self.assertRaises(ContractError): validate_deployment(self.deployment)

    def test_route_approved_synthetic_pass(self):
        self.ready()
        self.assertEqual(authorize_route(self.profile, self.provider, self.deployment,
            self.policy, "SYNTHETIC", "jsonSchema"), "AUTHORIZED_SIMULATION_ONLY")

    def test_sensitive_fallback_rejected(self):
        self.ready()
        with self.assertRaises(ContractError):
            authorize_route(self.profile, self.provider, self.deployment, self.policy, "CONFIDENTIAL", "jsonSchema")
        self.profile["fallbackDeploymentIds"] = ["other-deployment"]
        other = copy.deepcopy(self.provider); other["providerId"] = "other"
        with self.assertRaises(ContractError):
            authorize_route(self.profile, other, self.deployment, self.policy, "SYNTHETIC", "jsonSchema")

    def test_unapproved_egress_rejected(self):
        self.ready(); self.policy["approved"] = False
        with self.assertRaises(ContractError):
            authorize_route(self.profile, self.provider, self.deployment, self.policy, "SYNTHETIC", "jsonSchema")

    def test_profile_unknown_task_rejected(self):
        self.profile["taskType"] = "AUTO_PUBLISH"
        with self.assertRaises(ContractError): validate_profile(self.profile)

    def test_price_unknown_nan_negative_rejected(self):
        for value in [None, "NaN", "Infinity", "-1"]:
            c = dict(self.cost); c["inputUsdPerToken"] = value
            with self.assertRaises(ContractError): Budget(c)

    def test_budget_bool_limit_rejected(self):
        self.cost["maxRequests"] = True
        with self.assertRaises(ContractError): Budget(self.cost)

    def test_request_token_cost_time_concurrency_limits(self):
        for change, request in [({"maxRequests":0}, (1,1,0,0)),
                ({"maxInputTokens":0},(1,1,0,0)), ({"maxOutputTokens":0},(1,1,0,0)),
                ({"maxCostUsd":"0"},(1,1,0,0)), ({"maxSeconds":0},(1,1,1,0)),
                ({"maxRetries":0},(1,1,0,1)), ({"maxConcurrency":0},(1,1,0,0))]:
            with self.subTest(change=change):
                c=dict(self.cost);c.update(change);b=Budget(c)
                with self.assertRaises(ContractError): b.reserve("req",*request)

    def test_budget_reserve_and_no_refund_on_uncertain_failure(self):
        b=Budget(self.cost);b.reserve("req",2,3,0,0)
        self.assertEqual(b.cost, Fraction(1,125))
        b.finish("req", "NETWORK_FAILED")
        self.assertEqual(b.cost, Fraction(1,125))
        with self.assertRaises(ContractError): b.reserve("req",2,3,0,0)
        b.reserve("req2",2,3,1,1);b.finish("req2", "PASS")
        with self.assertRaises(ContractError): b.reserve("req3",2,3,1,0)

    def test_request_counts_validate(self):
        for value in [-1, True, 1.1]:
            with self.assertRaises(ContractError): Budget(self.cost).reserve("r",value,1,0,0)

    def test_fake_secret_not_in_any_visible_output(self):
        fake = "MOCK" + "_SECRET_" + "sensitive-fixture-only"
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            record=safe_record({"status":"AUTHENTICATION_FAILED", "requestId":"request-1",
                "headers":{"Authorization":fake},"exception":fake,"body":fake})
            rendered=json.dumps(record)
            try:
                p=copy.deepcopy(self.provider);p["apiKey"]=fake;validate_provider(p,self.policy)
            except ContractError as exc:
                rendered+=str(exc)
        self.assertNotIn(fake, stream.getvalue()+rendered)
        self.assertEqual(record, {"status":"AUTHENTICATION_FAILED"})

    def test_remote_error_body_never_recorded(self):
        for status in ["AUTHENTICATION_FAILED","INSUFFICIENT_BALANCE","RATE_LIMITED",
                       "TLS_FAILED","NETWORK_FAILED","MODEL_NOT_FOUND","SCHEMA_UNSUPPORTED",
                       "REFUSED","TRUNCATED","BUDGET_EXCEEDED","POLICY_DENIED"]:
            self.assertEqual(safe_record({"status":status,"detail":"untrusted"}),{"status":status})
        self.assertEqual(safe_record({"status":"secret-shaped-text"}),{"status":"UNKNOWN"})

    def resource(self):
        now=datetime.now(timezone.utc)
        resource=dict(taskId="G6-P0-PARSER-PREP-001",runId="run-1",owner="master",
            project="ontology-g6p0-parser-001",id="exact-volume",kind="volume",
            labels={"taskId":"G6-P0-PARSER-PREP-001","runId":"run-1"},fingerprint="a"*64,
            backend="engine-generation-1",references=[],keep=False,closed=True,synthetic=True,recoverable=True)
        plan=dict(taskId=resource["taskId"],runId="run-1",project=resource["project"],id=resource["id"],
            fingerprint=resource["fingerprint"],backend=resource["backend"],reviewed=True,
            createdAt=now.isoformat(),expiresAt=(now+timedelta(hours=1)).isoformat(),operation="DELETE_EXACT")
        return resource,plan,now

    def test_cleanup_foreign_keep_referenced_changed_backend(self):
        for field,value in [("taskId","G3-M5-001"),("runId","other"),("keep",True),
                ("references",["active-container"]),("backend","different"),
                ("fingerprint","b"*64),("closed",False),("synthetic",False),("recoverable",False)]:
            res,plan,now=self.resource();res[field]=value
            with self.assertRaises(ContractError):cleanup_eligible(res,plan,now)

    def test_cleanup_expired_unreviewed_global_rejected(self):
        for field,value in [("expiresAt","2000-01-01T00:00:00+00:00"),("reviewed",False),
                            ("operation","docker system prune"),("id","*")]:
            res,plan,now=self.resource();plan[field]=value
            with self.assertRaises(ContractError):cleanup_eligible(res,plan,now)

    def test_cleanup_dryrun_only(self):
        res,plan,now=self.resource()
        self.assertEqual(cleanup_eligible(res,plan,now),"ELIGIBLE_DRYRUN_ONLY")

    def test_compose_plan_valid_not_runnable(self):
        plan=json.loads((ROOT/"design/compose-plan.json").read_text())
        self.assertEqual(validate_compose(plan),"STATIC_PLAN_ONLY_RUNTIME_NOT_RUN")

    def test_compose_secret_privilege_socket_rejected(self):
        for field,value in [("privileged",True),("network_mode","host"),
                ("environment",{"API_KEY":"MOCK"+"_SECRET"}),
                ("volumes",["/var/run/docker.sock:/var/run/docker.sock"]),("user","0:0")]:
            plan=json.loads((ROOT/"design/compose-plan.json").read_text())
            plan["services"]["parser"][field]=value
            with self.assertRaises(ContractError):validate_compose(plan)

    def test_cost_never_rounds_under_budget(self):
        self.cost["inputUsdPerToken"] = "0.10000000000000000000000000001"
        with self.assertRaises(ContractError): Budget(self.cost).reserve("r",1,0,0,0)
        self.cost["inputUsdPerToken"] = "0.05000000000000000000000000001"
        b=Budget(self.cost); b.reserve("r",1,0,0,0); b.finish("r","PASS")
        with self.assertRaises(ContractError): b.reserve("r2",1,0,0,0)
        for price in ["1e999999999", "1e-999999999", "9"*129]:
            self.cost["inputUsdPerToken"]=price
            with self.assertRaises(ContractError): Budget(self.cost)

    def test_empty_url_delimiters_rejected_even_registered(self):
        for url in ["https://@api.openai.com/v1", "https://api.openai.com/v1?", "https://api.openai.com/v1#"]:
            self.provider["baseUrl"]=url; self.policy["endpoints"]=[url]
            with self.assertRaises(ContractError): validate_provider(self.provider,self.policy)

    def test_compose_exact_profiles_and_schema_type(self):
        for name in ["parser","ocr","ollama","eval","api"]:
            plan=json.loads((ROOT/"design/compose-plan.json").read_text())
            plan["services"][name]["profile"]="core" if name!="api" else "parser"
            with self.assertRaises(ContractError): validate_compose(plan)
        plan=json.loads((ROOT/"design/compose-plan.json").read_text());plan["schemaVersion"]=True
        with self.assertRaises(ContractError): validate_compose(plan)

    def test_malformed_shapes_only_fixed_errors(self):
        for obj, function in [(self.provider,lambda x:validate_provider(x,self.policy)),
                (self.deployment,validate_deployment),(self.profile,validate_profile)]:
            for key in obj:
                for bad in [[],{},None]:
                    mutated=copy.deepcopy(obj);mutated[key]=bad
                    try: function(mutated)
                    except ContractError as exc: self.assertRegex(str(exc),r"^[A-Z_]+$")
                    except Exception as exc: self.fail(type(exc).__name__)
        res,plan,now=self.resource()
        with self.assertRaises(ContractError): cleanup_eligible(res,plan,[])


if __name__ == "__main__":
    unittest.main()
