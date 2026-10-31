"""PREP 离线合同校验。没有网络、密钥存储、容器启动或资源删除实现。"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from functools import wraps
import re
from urllib.parse import urlsplit


class ContractError(ValueError):
    """异常只输出固定代码，永不拼接输入或远端异常。"""


def require(condition, code="CONTRACT_INVALID"):
    if not condition:
        raise ContractError(code)


def fields(value, names):
    require(type(value) is dict and set(value) == set(names.split()))


def integer(value, minimum=0):
    require(type(value) is int and value >= minimum)


def ident(value):
    require(type(value) is str and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", value))


def money(value):
    require(type(value) is str and len(value) <= 128, "PRICE_UNKNOWN")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ContractError("PRICE_UNKNOWN") from None
    require(result.is_finite() and result >= 0, "PRICE_UNKNOWN")
    require(abs(result.as_tuple().exponent) <= 128, "PRICE_UNKNOWN")
    return Fraction(result)


PROVIDERS = {"openai", "deepseek", "qwen", "glm", "kimi", "ollama"}
CAPABILITIES = {"text", "vision", "embedding", "jsonSchema", "tools", "streaming", "reasoning"}
STATUSES = {"UNKNOWN", "PASS", "FAIL"}
ERRORS = {"PASS", "AUTHENTICATION_FAILED", "INSUFFICIENT_BALANCE", "RATE_LIMITED",
          "TLS_FAILED", "NETWORK_FAILED", "MODEL_NOT_FOUND", "SCHEMA_UNSUPPORTED",
          "REFUSED", "TRUNCATED", "BUDGET_EXCEEDED", "POLICY_DENIED"}
TASKS = {"DOCUMENT_EXTRACTION", "ONTOLOGY_ALIGNMENT", "AGENT_REASONING", "EMBEDDING", "DOCUMENT_VISION"}


def validate_provider(provider, policy):
    """校验预登记端点和Secret引用；实际DNS/代理出口需后续容器验证。"""
    fields(provider, "providerId tenantScope providerType region baseUrl protocol secretRef allowedEgressPolicyId revision enabled")
    fields(policy, "policyId tenantScope providerId region endpoints dataClasses approved allowLocal")
    for key in ("providerId", "tenantScope", "region", "allowedEgressPolicyId"):
        ident(provider[key])
    integer(provider["revision"], 1)
    require(type(provider["enabled"]) is bool)
    require(provider["providerType"] in PROVIDERS)
    allowed_protocols = {"openai": {"responses", "chat"}, "ollama": {"ollama", "chat"}}
    require(provider["protocol"] in allowed_protocols.get(provider["providerType"], {"chat"}))
    require(policy["policyId"] == provider["allowedEgressPolicyId"] and
            all(policy[k] == provider[k] for k in ("tenantScope", "providerId", "region")), "POLICY_DENIED")
    require(type(policy["approved"]) is bool and type(policy["allowLocal"]) is bool)
    require(type(policy["endpoints"]) is list and type(policy["dataClasses"]) is list)
    require(all(type(x) is str for x in policy["endpoints"] + policy["dataClasses"]))
    url = provider["baseUrl"]
    require(type(url) is str and url.isascii() and not any(c.isspace() for c in url), "ENDPOINT_DENIED")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise ContractError("ENDPOINT_DENIED") from None
    require(parts.username is None and parts.password is None and "?" not in url and "#" not in url,
            "ENDPOINT_DENIED")
    require(url in policy["endpoints"] and "%" not in url and "\\" not in url, "ENDPOINT_DENIED")
    if provider["providerType"] == "ollama":
        require(policy["allowLocal"] and url in {"http://ollama:11434", "http://host.docker.internal:11434"}, "ENDPOINT_DENIED")
    else:
        require(parts.scheme == "https" and port in (None, 443) and parts.hostname and
                re.fullmatch(r"[a-z][a-z0-9.-]+\.[a-z]{2,}", parts.hostname) and
                parts.hostname not in {"localhost", "metadata.google.internal"} and
                not parts.hostname.endswith((".localhost", ".internal")), "ENDPOINT_DENIED")
    secret = provider["secretRef"]
    if secret is None:
        require(provider["providerType"] == "ollama", "SECRET_REF_REQUIRED")
    else:
        fields(secret, "id providerId tenantScope version mountPath")
        ident(secret["id"]); integer(secret["version"], 1)
        require(secret["providerId"] == provider["providerId"] and secret["tenantScope"] == provider["tenantScope"], "SECRET_SCOPE_DENIED")
        require(type(secret["mountPath"]) is str and re.fullmatch(r"/run/secrets/[a-z][a-z0-9_-]{0,63}", secret["mountPath"]), "SECRET_PATH_DENIED")
    return "CONFIG_VALID_ONLY"


def validate_deployment(deployment):
    fields(deployment, "deploymentId providerId modelId registrySnapshot capabilities authentication contextLimit probe")
    for key in ("deploymentId", "providerId", "modelId", "registrySnapshot"):
        ident(deployment[key])
    integer(deployment["contextLimit"], 1)
    require(type(deployment["capabilities"]) is dict and set(deployment["capabilities"]) == CAPABILITIES)
    require(all(x in STATUSES for x in deployment["capabilities"].values()))
    require(deployment["authentication"] in STATUSES)
    probe = deployment["probe"]
    if probe is not None:
        fields(probe, "providerId deploymentId modelId registrySnapshot schemaHash sampleVersion probeVersion capability status")
        require(all(probe[k] == deployment[k] for k in ("providerId", "deploymentId", "modelId", "registrySnapshot")), "STALE_PROBE")
        require(type(probe["schemaHash"]) is str and re.fullmatch(r"[0-9a-f]{64}", probe["schemaHash"]))
        ident(probe["sampleVersion"]); integer(probe["probeVersion"], 1)
        require(probe["capability"] in CAPABILITIES and probe["status"] in STATUSES)
    return "CONFIG_VALID_ONLY"


def validate_profile(profile):
    fields(profile, "profileId version taskType scope deploymentId fallbackDeploymentIds egressPolicyId costPolicyId schemaHash sampleVersion")
    for key in ("profileId", "scope", "deploymentId", "egressPolicyId", "costPolicyId", "sampleVersion"):
        ident(profile[key])
    integer(profile["version"], 1)
    require(profile["taskType"] in TASKS)
    require(type(profile["schemaHash"]) is str and re.fullmatch(r"[0-9a-f]{64}", profile["schemaHash"]))
    require(type(profile["fallbackDeploymentIds"]) is list)
    for item in profile["fallbackDeploymentIds"]: ident(item)
    require(len(set(profile["fallbackDeploymentIds"])) == len(profile["fallbackDeploymentIds"]))
    return "CONFIG_VALID_ONLY"


def authorize_route(profile, provider, deployment, policy, classification, capability):
    """单个目标重新验证，不执行回退或请求；费用必须另行经Budget预留。"""
    validate_profile(profile); validate_provider(provider, policy); validate_deployment(deployment)
    require(provider["enabled"] and policy["approved"] and classification in policy["dataClasses"], "POLICY_DENIED")
    require(profile["scope"] == provider["tenantScope"] and profile["egressPolicyId"] == policy["policyId"], "POLICY_DENIED")
    require(deployment["providerId"] == provider["providerId"] and deployment["deploymentId"] in
            [profile["deploymentId"], *profile["fallbackDeploymentIds"]], "POLICY_DENIED")
    require(capability in CAPABILITIES and deployment["authentication"] == "PASS" and
            deployment["capabilities"][capability] == "PASS", "CAPABILITY_UNKNOWN")
    probe = deployment["probe"]
    require(probe is not None and probe["capability"] == capability and probe["status"] == "PASS" and
            probe["schemaHash"] == profile["schemaHash"] and probe["sampleVersion"] == profile["sampleVersion"], "STALE_PROBE")
    return "AUTHORIZED_SIMULATION_ONLY"


class Budget:
    """内存顺序实验账本；预留最坏成本，不宣称分布式账本或真实计费。"""
    def __init__(self, policy):
        fields(policy, "maxRequests maxInputTokens maxOutputTokens maxCostUsd maxSeconds maxRetries maxConcurrency inputUsdPerToken outputUsdPerToken priceSnapshot currency")
        self.policy = dict(policy)
        for key in ("maxRequests", "maxInputTokens", "maxOutputTokens", "maxSeconds", "maxRetries", "maxConcurrency"):
            integer(policy[key])
        ident(policy["priceSnapshot"]); require(policy["currency"] == "USD")
        self.max_cost = money(policy["maxCostUsd"])
        self.input_price = money(policy["inputUsdPerToken"])
        self.output_price = money(policy["outputUsdPerToken"])
        self.requests = {}; self.active = set(); self.input_tokens = 0; self.output_tokens = 0
        self.cost = Fraction(0)

    def reserve(self, request_id, input_tokens, output_tokens, elapsed_seconds, retry):
        ident(request_id)
        for value in (input_tokens, output_tokens, elapsed_seconds, retry): integer(value)
        p = self.policy
        require(request_id not in self.requests, "DUPLICATE_REQUEST")
        amount = self.input_price * input_tokens + self.output_price * output_tokens
        require(len(self.requests) < p["maxRequests"] and len(self.active) < p["maxConcurrency"] and
                self.input_tokens + input_tokens <= p["maxInputTokens"] and
                self.output_tokens + output_tokens <= p["maxOutputTokens"] and
                self.cost + amount <= self.max_cost and elapsed_seconds <= p["maxSeconds"] and
                retry <= p["maxRetries"], "BUDGET_EXCEEDED")
        self.requests[request_id] = "RESERVED"; self.active.add(request_id)
        self.input_tokens += input_tokens; self.output_tokens += output_tokens; self.cost += amount
        return "RESERVED_SIMULATION_ONLY"

    def finish(self, request_id, status):
        require(request_id in self.active and status in ERRORS)
        self.active.remove(request_id); self.requests[request_id] = status
        # 远端结果不明仍保留全部预留，不以失败为由虚构退款。


def safe_record(raw):
    """只输出有限枚举；业务ID不因格式看似安全就自动允许进入遥测。"""
    status = raw.get("status") if type(raw) is dict else None
    return {"status": status if type(status) is str and status in ERRORS else "UNKNOWN"}


def cleanup_eligible(resource, plan, now):
    """纯内存DryRun资格；没有subprocess、Docker client或删除函数。"""
    fields(resource, "taskId runId owner project id kind labels fingerprint backend references keep closed synthetic recoverable")
    fields(plan, "taskId runId project id fingerprint backend reviewed createdAt expiresAt operation")
    require(resource["taskId"] == "G6-P0-PARSER-PREP-001" and resource["kind"] in {"volume", "container", "network"}, "RESOURCE_SCOPE_DENIED")
    require(resource["project"] == "ontology-g6p0-parser-001")
    for key in ("taskId", "runId", "project", "id", "fingerprint", "backend"):
        require(resource[key] == plan[key], "RESOURCE_CHANGED")
    for key in ("id", "runId", "owner", "backend"): ident(resource[key])
    require(type(resource["fingerprint"]) is str and re.fullmatch(r"[0-9a-f]{64}", resource["fingerprint"]))
    require(resource["labels"] == {"taskId":resource["taskId"], "runId":resource["runId"]})
    require(resource["references"] == [] and resource["keep"] is False and
            all(resource[k] is True for k in ("closed", "synthetic", "recoverable")), "RESOURCE_KEEP")
    require(plan["reviewed"] is True and plan["operation"] == "DELETE_EXACT", "PLAN_DENIED")
    try:
        start, end = (datetime.fromisoformat(plan[k]) for k in ("createdAt", "expiresAt"))
    except (ValueError, TypeError):
        raise ContractError("PLAN_TIME_INVALID") from None
    require(all(t.tzinfo is not None and t.utcoffset() == timedelta(0) for t in (start,end,now)), "PLAN_TIME_INVALID")
    require(start <= now < end and end-start <= timedelta(hours=24), "PLAN_EXPIRED")
    return "ELIGIBLE_DRYRUN_ONLY"


def validate_compose(plan):
    """设计结构检查，不是docker compose配置解析或实际安全隔离证明。"""
    fields(plan, "schemaVersion runnable platforms services lifecycle")
    require(type(plan["schemaVersion"]) is int and plan["schemaVersion"] == 1 and plan["runnable"] is False)
    require(plan["platforms"] == ["linux/arm64", "linux/amd64"])
    require(type(plan["services"]) is dict and set(plan["services"]) ==
            {"web", "api", "postgres", "jena", "rustfs", "keycloak", "otel", "parser", "ocr", "ollama", "eval"})
    for name, service in plan["services"].items():
        fields(service, "profile image imageStatus user read_only cap_drop security_opt networks ports secrets healthcheck memLimitMiB cpuLimit tmpfs")
        require(service["profile"] == (name if name in {"parser", "ocr", "ollama", "eval"} else "core"))
        require(service["image"] is None and service["imageStatus"] == "BLOCKED_PENDING_DIGEST")
        require(service["user"] == "10001:10001" and service["read_only"] is True)
        require(service["cap_drop"] == ["ALL"] and service["security_opt"] == ["no-new-privileges:true"])
        require(service["networks"] == ["internal"])
        require(service["ports"] == (["127.0.0.1:8080:8080"] if name == "api" else []))
        require(service["secrets"] == (["provider_secret_ref"] if name == "api" else []))
        fields(service["healthcheck"], "test intervalSeconds timeoutSeconds retries startPeriodSeconds")
        require(type(service["healthcheck"]["test"]) is list and service["healthcheck"]["test"])
        for k in ("intervalSeconds", "timeoutSeconds", "retries", "startPeriodSeconds"): integer(service["healthcheck"][k],1)
        integer(service["memLimitMiB"],1);integer(service["cpuLimit"],1)
        require(service["tmpfs"] == ["/tmp:rw,noexec,nosuid,size=64m"])
    require(plan["lifecycle"] == "EXACT_REVIEWED_TASK_RUN_ONLY")
    return "STATIC_PLAN_ONLY_RUNTIME_NOT_RUN"


def safe_boundary(function):
    """所有公开离线入口将坏形状的标准库异常收敛为固定错误码。"""
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ContractError:
            raise
        except (TypeError, ValueError, KeyError, AttributeError, OverflowError, ArithmeticError, RecursionError):
            raise ContractError("CONTRACT_INVALID") from None
    return checked


for _entry in ("validate_provider", "validate_deployment", "validate_profile", "authorize_route", "cleanup_eligible", "validate_compose"):
    globals()[_entry] = safe_boundary(globals()[_entry])
Budget.__init__ = safe_boundary(Budget.__init__)
Budget.reserve = safe_boundary(Budget.reserve)
Budget.finish = safe_boundary(Budget.finish)
