"""
PiBot V3 - LLM Client Adapter
OpenAI-compatible adapter for Agent Core

Supports multiple providers:
- Volcengine (default)
- OpenAI
- DeepSeek
- Other OpenAI-compatible APIs
"""

import os
import json
import asyncio
from typing import Any, Dict, List, Optional, AsyncGenerator
import logging

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM client for Agent Core."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: int = 60,
        max_retries: int = 2,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

        # Import openai here to avoid dependency issues
        try:
            import openai

            self.client = openai.AsyncOpenAI(
                api_key=api_key, base_url=base_url, timeout=timeout
            )
        except ImportError:
            logger.warning("OpenAI library not installed, using HTTP fallback")
            self.client = None

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """
        Get chat completion from LLM.

        Returns response in standardized format:
        {
            "content": [  # List of content blocks
                {"type": "text", "text": "..."},
                {"type": "tool_call", "id": "...", "name": "...", "arguments": {...}}
            ],
            "stop_reason": "endTurn" | "toolCalls" | "error",
            "model": "model-name",
            "usage": {"prompt_tokens": N, "completion_tokens": N}
        }
        """
        if self.client:
            return await self._call_openai(
                messages, tools, temperature, max_tokens, stream
            )
        else:
            return await self._call_http(
                messages, tools, temperature, max_tokens, stream
            )

    def _convert_messages_for_volcengine(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert messages to Volcengine-compatible format.

        Volcengine API doesn't support 'tool_call' content type or 'tool' role.
        """
        converted = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")

            # Handle 'tool' role - convert to 'user' with tool result info
            if role == "tool":
                tool_id = msg.get("tool_call_id", "unknown")
                content_str = content if isinstance(content, str) else str(content)
                converted.append(
                    {
                        "role": "user",
                        "content": f"[Tool Result {tool_id}]: {content_str}",
                    }
                )
                continue

            # Handle assistant with list content (may contain tool_calls)
            if role == "assistant" and isinstance(content, list):
                text_parts = []
                for item in content:
                    if item.get("type") == "text" and item.get("text"):
                        text_parts.append(item["text"])
                    elif item.get("type") == "tool_call":
                        tool_name = item.get("name", "unknown")
                        tool_id = item.get("id", "unknown")
                        tool_info = f"[Calling tool: {tool_name} (ID: {tool_id})]"
                        text_parts.append(tool_info)
                converted.append(
                    {
                        "role": "assistant",
                        "content": "\n".join(text_parts) if text_parts else "",
                    }
                )
                continue

            # For other messages, ensure content is a string
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                content = "\n".join(text_parts)

            converted.append(
                {
                    "role": role,
                    "content": content if isinstance(content, str) else str(content),
                }
            )

        return converted

    async def _call_openai(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        temperature: float,
        max_tokens: Optional[int],
        stream: bool,
    ) -> Dict[str, Any]:
        """Call OpenAI-compatible API."""
        # Convert messages for Volcengine compatibility
        converted_messages = self._convert_messages_for_volcengine(messages)

        params = {
            "model": self.model,
            "messages": converted_messages,
            "temperature": temperature,
            "stream": stream,
        }

        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"

        if max_tokens:
            params["max_tokens"] = max_tokens

        retries = 0
        last_error = None

        while retries < self.max_retries:
            try:
                response = await self.client.chat.completions.create(**params)
                return self._parse_response(response)
            except Exception as e:
                last_error = e
                logger.warning(f"LLM call failed (attempt {retries + 1}): {e}")
                retries += 1
                if retries < self.max_retries:
                    await asyncio.sleep(1 * retries)  # Exponential backoff

        # All retries failed
        logger.error(f"LLM call failed after {self.max_retries} attempts: {last_error}")
        return {
            "content": [
                {"type": "text", "text": f"Error: LLM call failed - {last_error}"}
            ],
            "stop_reason": "error",
            "model": self.model,
            "usage": {},
        }

    async def _call_http(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        temperature: float,
        max_tokens: Optional[int],
        stream: bool,
    ) -> Dict[str, Any]:
        """Fallback HTTP implementation using aiohttp."""
        try:
            import aiohttp
        except ImportError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Error: Neither openai nor aiohttp installed",
                    }
                ],
                "stop_reason": "error",
                "model": self.model,
                "usage": {},
            }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        if max_tokens:
            payload["max_tokens"] = max_tokens

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        retries = 0
        last_error = None

        while retries < self.max_retries:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=self.timeout),
                    ) as response:
                        if response.status != 200:
                            text = await response.text()
                            raise Exception(f"HTTP {response.status}: {text}")

                        data = await response.json()
                        return self._parse_http_response(data)
            except Exception as e:
                last_error = e
                logger.warning(f"HTTP LLM call failed (attempt {retries + 1}): {e}")
                retries += 1
                if retries < self.max_retries:
                    await asyncio.sleep(1 * retries)

        logger.error(
            f"HTTP LLM call failed after {self.max_retries} attempts: {last_error}"
        )
        return {
            "content": [
                {"type": "text", "text": f"Error: HTTP LLM call failed - {last_error}"}
            ],
            "stop_reason": "error",
            "model": self.model,
            "usage": {},
        }

    def _parse_response(self, response: Any) -> Dict[str, Any]:
        """Parse OpenAI response to standardized format."""
        try:
            choice = response.choices[0]
            message = choice.message

            content_blocks = []

            # Handle text content
            if message.content:
                content_blocks.append({"type": "text", "text": message.content})

            # Handle tool calls
            if message.tool_calls:
                for tool_call in message.tool_calls:
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        arguments = {"raw": tool_call.function.arguments}

                    content_blocks.append(
                        {
                            "type": "tool_call",
                            "id": tool_call.id,
                            "name": tool_call.function.name,
                            "arguments": arguments,
                        }
                    )

            # Determine stop reason
            stop_reason_map = {
                "stop": "endTurn",
                "length": "endTurn",
                "tool_calls": "toolCalls",
                "content_filter": "error",
            }
            stop_reason = stop_reason_map.get(choice.finish_reason, "endTurn")

            return {
                "content": content_blocks,
                "stop_reason": stop_reason,
                "model": response.model,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens
                    if response.usage
                    else 0,
                    "completion_tokens": response.usage.completion_tokens
                    if response.usage
                    else 0,
                },
            }
        except Exception as e:
            logger.error(f"Error parsing response: {e}")
            return {
                "content": [{"type": "text", "text": f"Error parsing response: {e}"}],
                "stop_reason": "error",
                "model": self.model,
                "usage": {},
            }

    def _parse_http_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse HTTP JSON response to standardized format."""
        try:
            choice = data["choices"][0]
            message = choice["message"]

            content_blocks = []

            if message.get("content"):
                content_blocks.append({"type": "text", "text": message["content"]})

            if message.get("tool_calls"):
                for tool_call in message["tool_calls"]:
                    try:
                        arguments = json.loads(tool_call["function"]["arguments"])
                    except json.JSONDecodeError:
                        arguments = {"raw": tool_call["function"]["arguments"]}

                    content_blocks.append(
                        {
                            "type": "tool_call",
                            "id": tool_call["id"],
                            "name": tool_call["function"]["name"],
                            "arguments": arguments,
                        }
                    )

            stop_reason_map = {
                "stop": "endTurn",
                "length": "endTurn",
                "tool_calls": "toolCalls",
                "content_filter": "error",
            }
            stop_reason = stop_reason_map.get(choice.get("finish_reason"), "endTurn")

            usage = data.get("usage", {})

            return {
                "content": content_blocks,
                "stop_reason": stop_reason,
                "model": data.get("model", self.model),
                "usage": {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                },
            }
        except Exception as e:
            logger.error(f"Error parsing HTTP response: {e}")
            return {
                "content": [{"type": "text", "text": f"Error parsing response: {e}"}],
                "stop_reason": "error",
                "model": self.model,
                "usage": {},
            }


class VolcengineClient(LLMClient):
    """Volcengine-specific client with optimized defaults."""

    def __init__(
        self,
        api_key: str,
        model: str = "doubao-seed-code",
        base_url: str = "https://ark.cn-beijing.volces.com/api/coding/v3",
        **kwargs,
    ):
        super().__init__(api_key=api_key, base_url=base_url, model=model, **kwargs)


class DeepSeekClient(LLMClient):
    """DeepSeek-specific client."""

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com/v1",
        **kwargs,
    ):
        super().__init__(api_key=api_key, base_url=base_url, model=model, **kwargs)


# ============================================================================
# Integration with Agent Core
# ============================================================================

from agent_core import AgentCore


class AgentCoreWithLLM(AgentCore):
    """Agent Core with integrated LLM client."""

    def __init__(self, context, llm_client: LLMClient, **kwargs):
        super().__init__(context, llm_client, **kwargs)
        self.llm_client = llm_client

    async def _call_llm(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Call LLM via the client."""
        return await self.llm_client.chat_completion(
            messages=messages, tools=tools if tools else None
        )


# ============================================================================
# Factory Functions
# ============================================================================


def create_llm_client_from_env() -> Optional[LLMClient]:
    """Create LLM client from environment variables."""
    api_key = os.environ.get("VOLC_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("No API key found in environment (VOLC_API_KEY or OPENAI_API_KEY)")
        return None

    # Detect provider from base_url
    base_url = os.environ.get(
        "VOLC_BASE_URL", os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    )

    model = os.environ.get("MODEL_NAME", "gpt-3.5-turbo")

    if "volces.com" in base_url:
        return VolcengineClient(api_key=api_key, model=model, base_url=base_url)
    elif "deepseek" in base_url:
        return DeepSeekClient(api_key=api_key, model=model, base_url=base_url)
    else:
        return LLMClient(api_key=api_key, model=model, base_url=base_url)


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    # Test the client
    import asyncio

    async def test():
        client = create_llm_client_from_env()
        if client:
            response = await client.chat_completion(
                [{"role": "user", "content": "Say hello"}]
            )
            print(json.dumps(response, indent=2, ensure_ascii=False))
        else:
            print("No client created - check environment variables")

    asyncio.run(test())
