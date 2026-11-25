"""`python -m ontology_platform.modules.ai.check`: can this container reach the models?

One small structured call per configured model, with the reasoning effort the extraction uses
for it (spec 004, 7.3), so that an effort a model does not accept shows up here. Prints only
whether it works, the model, the effort and an error type: never the key or the proxy.
Exit code 0 when every call succeeds, 1 otherwise.
"""

import asyncio
import sys

from pydantic import BaseModel

from ontology_platform.modules.ai.gateway import AiError, OpenAIGateway
from ontology_platform.settings import Settings, effort_value


class Pong(BaseModel):
    reply: str


async def check() -> int:
    settings = Settings()
    if not settings.ai_configured:
        print("AI 未配置：.env.local 中没有 OP_OPENAI_API_KEY")
        return 1
    via = "经代理" if settings.ai_proxy else "直连"
    gateway = OpenAIGateway(settings)
    code = 0
    for model, effort in (
        (settings.ai_model, settings.ai_effort),
        (settings.ai_reasoning_model, settings.ai_reasoning_effort),
    ):
        try:
            result = await gateway.structured(
                purpose="status.check",
                model=model,
                instructions="Reply with the single word pong.",
                text="ping",
                schema=Pong,
                effort=effort_value(effort),
            )
        except AiError as exc:
            print(f"AI 不可用（{via}，模型 {model}，推理强度 {effort}）：{exc.code}，{exc}")
            code = 1
            continue
        print(f"AI 可用（{via}，模型 {model}，推理强度 {effort}）：回复 {result.reply!r}")
    return code


if __name__ == "__main__":
    sys.exit(asyncio.run(check()))
