"""`python -m ontology_platform.modules.ai.check`: can this container reach the model?

Prints only whether it works, the model name and an error type: never the key or the proxy.
Exit code 0 when a small structured call succeeds, 1 otherwise.
"""

import asyncio
import sys

from pydantic import BaseModel

from ontology_platform.modules.ai.gateway import AiError, OpenAIGateway
from ontology_platform.settings import Settings


class Pong(BaseModel):
    reply: str


async def check() -> int:
    settings = Settings()
    if not settings.ai_configured:
        print("AI 未配置：.env.local 中没有 OP_OPENAI_API_KEY")
        return 1
    via = "经代理" if settings.ai_proxy else "直连"
    gateway = OpenAIGateway(settings)
    try:
        result = await gateway.structured(
            purpose="status.check",
            model=settings.ai_model,
            instructions="Reply with the single word pong.",
            text="ping",
            schema=Pong,
        )
    except AiError as exc:
        cause = type(exc.__cause__).__name__ if exc.__cause__ else type(exc).__name__
        print(f"AI 不可用（{via}，模型 {settings.ai_model}）：{exc.code}，{cause}")
        return 1
    print(f"AI 可用（{via}，模型 {settings.ai_model}）：回复 {result.reply!r}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(check()))
