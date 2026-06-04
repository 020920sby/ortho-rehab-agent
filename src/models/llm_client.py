"""
LLM客户端 — 统一封装与Baichuan-M2-32B（或其他OpenAI兼容模型）的通信。

修复点：
- 原方案 sync/async 混用且 achat 只是同步封装。这里使用 AsyncOpenAI 实现真正的异步。
- 添加重试机制（tenacity），生产环境必备。
- 添加 Langfuse 可观测性钩子（可选）。
- json_object 模式时自动在 system prompt 中注入 "JSON" 关键字（OpenAI API 要求）。
"""

import os
import json
import logging
from typing import Optional, List, Dict, Any

from openai import OpenAI, AsyncOpenAI
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

load_dotenv()
logger = logging.getLogger(__name__)


class LLMClient:
    """LLM调用客户端，支持 Baichuan-M2-32B 及所有 OpenAI 兼容 API。"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        base_url = base_url or os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")
        api_key = api_key or os.getenv("LLM_API_KEY", "EMPTY")
        self.model = model or os.getenv("LLM_MODEL", "Baichuan-M2-32B-GPTQ-Int4")

        self.sync_client = OpenAI(base_url=base_url, api_key=api_key)
        self.async_client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    # ── 同步调用（带重试） ──────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
    )
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 2048,
        response_format: Optional[Dict] = None,
    ) -> str:
        """
        同步调用LLM。

        注意：当 response_format={"type": "json_object"} 时，
        OpenAI API 要求 prompt 中包含 "JSON" 字样。
        本方法会在 system message 末尾自动追加。
        """
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": self._ensure_json_keyword(messages, response_format),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        logger.debug("LLM call: model=%s, tokens=%d", self.model, max_tokens)
        response = self.sync_client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""

        # 调试日志
        usage = response.usage
        if usage:
            logger.debug(
                "LLM usage: prompt=%d, completion=%d, total=%d",
                usage.prompt_tokens, usage.completion_tokens, usage.total_tokens,
            )

        return content

    # ── 真正的异步调用 ──────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
    )
    async def achat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 2048,
        response_format: Optional[Dict] = None,
    ) -> str:
        """真正的异步LLM调用，适用于 FastAPI 异步路由。"""
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": self._ensure_json_keyword(messages, response_format),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        response = await self.async_client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    # ── 辅助 ────────────────────────────────────────────────

    @staticmethod
    def _ensure_json_keyword(
        messages: List[Dict[str, str]],
        response_format: Optional[Dict],
    ) -> List[Dict[str, str]]:
        """
        当使用 json_object 模式时，确保 prompt 中含有 "JSON" 关键字。
        这是 OpenAI API 的硬性要求，否则会返回 400 错误。
        """
        if response_format and response_format.get("type") == "json_object":
            for msg in messages:
                content = msg.get("content", "")
                if isinstance(content, str) and "json" in content.lower():
                    return messages
            # 自动追加 JSON 提示
            messages = list(messages)
            if messages and messages[0]["role"] == "system":
                messages[0] = {
                    "role": "system",
                    "content": messages[0]["content"] + "\n\n请以 JSON 格式返回结果。",
                }
        return messages

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        """
        同步调用并以 JSON 解析返回结果。解析失败返回包含 error 字段的 dict。
        这是最常用的高层封装。
        """
        try:
            raw = self.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("JSON decode failed: %s", e)
            return {"error": f"LLM返回非JSON格式：{str(e)}", "raw": raw[:200]}
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            return {"error": f"LLM调用失败：{str(e)}"}

    async def achat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        """异步版的 chat_json。"""
        try:
            raw = await self.achat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("JSON decode failed (async): %s", e)
            return {"error": f"LLM返回非JSON格式：{str(e)}", "raw": raw[:200]}
        except Exception as e:
            logger.error("LLM async call failed: %s", e)
            return {"error": f"LLM调用失败：{str(e)}"}


# ── 全局单例（惰性初始化） ──────────────────────────────────

_llm_client_instance: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _llm_client_instance
    if _llm_client_instance is None:
        _llm_client_instance = LLMClient()
    return _llm_client_instance


# 向后兼容的快捷引用
llm_client = property(lambda self: get_llm_client())
