"""
PiBot V3 - Agent Core
Based on pi-mono agent-loop.ts pattern

Provides the core agent loop with:
- Streaming LLM responses
- Tool execution
- Message lifecycle management
- Event streaming for UI updates
"""

import os
import json
import asyncio
from typing import Any, Dict, List, Optional, Callable, AsyncGenerator, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging
import uuid

logger = logging.getLogger(__name__)


class AgentRole(Enum):
    """Agent role in the system."""

    MASTER = "master"
    WORKER = "worker"


class MessageType(Enum):
    """Types of message content."""

    TEXT = "text"
    TOOL_CALL = "toolCall"
    IMAGE = "image"
    THINKING = "thinking"


class StopReason(Enum):
    """Reason why assistant stopped generating."""

    END_TURN = "endTurn"
    STOP = "stop"
    ERROR = "error"
    ABORTED = "aborted"
    TOOL_CALLS = "toolCalls"


@dataclass
class ToolCall:
    """A tool call from the assistant."""

    id: str
    name: str
    arguments: Dict[str, Any]

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())


@dataclass
class MessageContent:
    """Content block in a message."""

    type: MessageType
    text: Optional[str] = None
    tool_call: Optional[ToolCall] = None
    image_data: Optional[str] = None  # base64 encoded
    thinking: Optional[str] = None


@dataclass
class AgentMessage:
    """Base message class for agent conversations."""

    role: str  # "user", "assistant", "toolResult", "system"
    content: List[MessageContent] = field(default_factory=list)
    timestamp: int = field(
        default_factory=lambda: int(datetime.now().timestamp() * 1000)
    )
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Tool result specific fields
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    is_error: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Result from a tool execution."""

    content: List[MessageContent]
    details: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def text(cls, text: str, details: Optional[Dict[str, Any]] = None) -> "ToolResult":
        """Create a text result."""
        return cls(
            content=[MessageContent(type=MessageType.TEXT, text=text)],
            details=details if details is not None else {},
        )

    @classmethod
    def error(
        cls, error: str, details: Optional[Dict[str, Any]] = None
    ) -> "ToolResult":
        """Create an error result."""
        return cls(
            content=[MessageContent(type=MessageType.TEXT, text=f"Error: {error}")],
            details=details if details is not None else {},
        )


@dataclass
class AgentTool:
    """A tool that can be executed by the agent."""

    name: str
    label: str
    description: str
    input_schema: Dict[str, Any]  # JSON Schema
    execute: Callable[[str, Dict[str, Any]], Any]  # tool_call_id, params -> result

    def validate_args(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Validate tool arguments against schema."""
        # Basic validation - can be enhanced with jsonschema library
        required = self.input_schema.get("required", [])
        for field_name in required:
            if field_name not in args:
                raise ValueError(f"Missing required argument: {field_name}")

        properties = self.input_schema.get("properties", {})
        for key, value in args.items():
            if key not in properties:
                raise ValueError(f"Unknown argument: {key}")

            prop_type = properties[key].get("type")
            if prop_type == "string" and not isinstance(value, str):
                raise ValueError(
                    f"Expected string for {key}, got {type(value).__name__}"
                )
            elif prop_type == "number" and not isinstance(value, (int, float)):
                raise ValueError(
                    f"Expected number for {key}, got {type(value).__name__}"
                )
            elif prop_type == "boolean" and not isinstance(value, bool):
                raise ValueError(
                    f"Expected boolean for {key}, got {type(value).__name__}"
                )
            elif prop_type == "array" and not isinstance(value, list):
                raise ValueError(
                    f"Expected array for {key}, got {type(value).__name__}"
                )
            elif prop_type == "object" and not isinstance(value, dict):
                raise ValueError(
                    f"Expected object for {key}, got {type(value).__name__}"
                )

        return args


@dataclass
class AgentContext:
    """Context for agent execution."""

    system_prompt: str
    messages: List[AgentMessage] = field(default_factory=list)
    tools: List[AgentTool] = field(default_factory=list)
    role: AgentRole = AgentRole.MASTER

    def add_message(self, message: AgentMessage):
        """Add a message to the context."""
        self.messages.append(message)

    def get_tool(self, name: str) -> Optional[AgentTool]:
        """Get a tool by name."""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    def to_llm_messages(self) -> List[Dict[str, Any]]:
        """Convert messages to LLM-compatible format."""
        llm_messages = []

        for msg in self.messages:
            if msg.role == "system":
                content_str = ""
                if msg.content:
                    for c in msg.content:
                        if c.text:
                            content_str += c.text
                llm_messages.append({"role": "system", "content": content_str})
            elif msg.role == "user":
                content_str = ""
                for c in msg.content:
                    if c.type == MessageType.TEXT and c.text:
                        content_str += c.text
                    elif c.type == MessageType.IMAGE and c.image_data:
                        content_str += f"[Image: {c.image_data[:50]}...]"
                llm_messages.append({"role": "user", "content": content_str})
            elif msg.role == "assistant":
                content = []
                for c in msg.content:
                    if c.type == MessageType.TEXT and c.text:
                        content.append({"type": "text", "text": c.text})
                    elif c.type == MessageType.TOOL_CALL and c.tool_call:
                        content.append(
                            {
                                "type": "tool_call",
                                "id": c.tool_call.id,
                                "name": c.tool_call.name,
                                "arguments": c.tool_call.arguments,
                            }
                        )
                llm_messages.append({"role": "assistant", "content": content})
            elif msg.role == "toolResult":
                content_str = ""
                for c in msg.content:
                    if c.type == MessageType.TEXT and c.text:
                        content_str += c.text
                llm_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg.tool_call_id,
                        "content": content_str,
                    }
                )

        return llm_messages

    def to_tools_schema(self) -> List[Dict[str, Any]]:
        """Convert tools to LLM-compatible format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in self.tools
        ]


class AgentEvent:
    """Event emitted by the agent."""

    def __init__(self, event_type: str, **data):
        self.type = event_type
        self.timestamp = int(datetime.now().timestamp() * 1000)
        self.data = data

    def __repr__(self):
        return f"AgentEvent({self.type}, {self.data.keys()})"


class AgentEventStream:
    """Stream of agent events."""

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._closed = False
        self._subscribers: List[Callable] = []

    def subscribe(self, callback: Callable[[AgentEvent], None]):
        """Subscribe to events."""
        self._subscribers.append(callback)

    def push(self, event: AgentEvent):
        """Push an event to the stream."""
        if self._closed:
            return

        self._queue.put_nowait(event)
        for callback in self._subscribers:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Error in event subscriber: {e}")

    async def get(self) -> Optional[AgentEvent]:
        """Get the next event from the stream."""
        if self._closed and self._queue.empty():
            return None
        return await self._queue.get()

    def close(self):
        """Close the stream."""
        self._closed = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._closed and self._queue.empty():
            raise StopAsyncIteration
        return await self._queue.get()


class AgentCore:
    """Core agent loop implementing the pi-mono pattern."""

    def __init__(
        self,
        context: AgentContext,
        llm_client: Any,  # LLM client (e.g., OpenAI-compatible)
        max_iterations: int = 10,
        get_steering_messages: Optional[Callable[[], List[AgentMessage]]] = None,
        get_follow_up_messages: Optional[Callable[[], List[AgentMessage]]] = None,
    ):
        self.context = context
        self.llm_client = llm_client
        self.max_iterations = max_iterations
        self.get_steering_messages = get_steering_messages
        self.get_follow_up_messages = get_follow_up_messages
        self._abort_event = asyncio.Event()

    def abort(self):
        """Signal the agent to stop."""
        self._abort_event.set()

    async def run(
        self, prompts: List[AgentMessage], stream: AgentEventStream
    ) -> List[AgentMessage]:
        """Run the agent loop with new prompts."""
        new_messages: List[AgentMessage] = []

        # Add prompts to context
        for prompt in prompts:
            self.context.add_message(prompt)
            new_messages.append(prompt)

        # Push start events
        stream.push(AgentEvent("agent_start", role=self.context.role.value))
        stream.push(AgentEvent("turn_start"))

        for prompt in prompts:
            stream.push(AgentEvent("message_start", message=prompt))
            stream.push(AgentEvent("message_end", message=prompt))

        # Run the main loop
        await self._run_loop(new_messages, stream)

        return new_messages

    async def _run_loop(
        self, new_messages: List[AgentMessage], stream: AgentEventStream
    ):
        """Main agent loop."""
        iteration = 0
        pending_messages: List[AgentMessage] = []

        if self.get_steering_messages:
            pending_messages = self.get_steering_messages()

        while iteration < self.max_iterations:
            iteration += 1

            # Check for abort
            if self._abort_event.is_set():
                stream.push(
                    AgentEvent("agent_end", messages=new_messages, reason="aborted")
                )
                stream.close()
                return

            has_more_tool_calls = True
            steering_after_tools: Optional[List[AgentMessage]] = None

            # Inner loop: process tool calls
            while has_more_tool_calls or pending_messages:
                if iteration > 1:
                    stream.push(AgentEvent("turn_start"))

                # Process pending steering messages
                if pending_messages:
                    for message in pending_messages:
                        stream.push(AgentEvent("message_start", message=message))
                        stream.push(AgentEvent("message_end", message=message))
                        self.context.add_message(message)
                        new_messages.append(message)
                    pending_messages = []

                # Stream assistant response
                try:
                    message = await self._stream_assistant_response(stream)
                    new_messages.append(message)

                    if message.role == "assistant":
                        stop_reason = getattr(
                            message, "stop_reason", StopReason.END_TURN
                        )
                        if stop_reason in (StopReason.ERROR, StopReason.ABORTED):
                            stream.push(
                                AgentEvent("turn_end", message=message, tool_results=[])
                            )
                            stream.push(AgentEvent("agent_end", messages=new_messages))
                            stream.close()
                            return
                except Exception as e:
                    logger.error(f"Error streaming assistant response: {e}")
                    error_msg = AgentMessage(
                        role="assistant",
                        content=[
                            MessageContent(
                                type=MessageType.TEXT, text=f"Error: {str(e)}"
                            )
                        ],
                    )
                    new_messages.append(error_msg)
                    stream.push(
                        AgentEvent("agent_end", messages=new_messages, error=str(e))
                    )
                    stream.close()
                    return

                # Check for tool calls
                tool_calls = [
                    c
                    for c in message.content
                    if c.type == MessageType.TOOL_CALL and c.tool_call
                ]
                has_more_tool_calls = len(tool_calls) > 0

                if has_more_tool_calls:
                    tool_results = await self._execute_tool_calls(
                        tool_calls, stream, message
                    )

                    for result_msg in tool_results:
                        self.context.add_message(result_msg)
                        new_messages.append(result_msg)

                stream.push(
                    AgentEvent("turn_end", message=message, tool_results=tool_calls)
                )

                # Get steering messages after turn
                if steering_after_tools:
                    pending_messages = steering_after_tools
                    steering_after_tools = None
                elif self.get_steering_messages:
                    pending_messages = self.get_steering_messages()

            # Check for follow-up messages
            if self.get_follow_up_messages:
                follow_up = self.get_follow_up_messages()
                if follow_up:
                    pending_messages = follow_up
                    continue

            # No more messages, exit
            break

        stream.push(AgentEvent("agent_end", messages=new_messages))
        stream.close()

    async def _stream_assistant_response(
        self, stream: AgentEventStream
    ) -> AgentMessage:
        """Stream an assistant response from the LLM."""
        # Prepare LLM context
        llm_messages = self.context.to_llm_messages()
        tools = self.context.to_tools_schema()

        # Call LLM
        try:
            response = await self._call_llm(llm_messages, tools)

            # Create assistant message
            assistant_msg = AgentMessage(role="assistant")

            # Convert response content to MessageContent
            content_blocks = []
            for block in response.get("content", []):
                if isinstance(block, dict):
                    block_type = block.get("type", "text")
                    if block_type == "text":
                        content_blocks.append(
                            MessageContent(
                                type=MessageType.TEXT, text=block.get("text", "")
                            )
                        )
                    elif block_type == "tool_call":
                        content_blocks.append(
                            MessageContent(
                                type=MessageType.TOOL_CALL,
                                tool_call=ToolCall(
                                    id=block.get("id", str(uuid.uuid4())),
                                    name=block.get("name", ""),
                                    arguments=block.get("arguments", {}),
                                ),
                            )
                        )
                    elif block_type == "thinking":
                        content_blocks.append(
                            MessageContent(
                                type=MessageType.THINKING,
                                thinking=block.get("thinking", ""),
                            )
                        )

            assistant_msg.content = content_blocks

            # Push events
            stream.push(AgentEvent("message_start", message=assistant_msg))
            stream.push(AgentEvent("message_end", message=assistant_msg))

            # Add to context
            self.context.add_message(assistant_msg)

            return assistant_msg

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            error_msg = AgentMessage(
                role="assistant",
                content=[
                    MessageContent(type=MessageType.TEXT, text=f"Error: {str(e)}")
                ],
            )
            return error_msg

    async def _call_llm(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Call the LLM. Override this method for different LLM providers."""
        # This is a placeholder - actual implementation depends on LLM client
        raise NotImplementedError("Subclasses must implement _call_llm")

    async def _execute_tool_calls(
        self,
        tool_call_contents: List[MessageContent],
        stream: AgentEventStream,
        assistant_message: AgentMessage,
    ) -> List[AgentMessage]:
        """Execute tool calls from the assistant message."""
        results: List[AgentMessage] = []

        for content in tool_call_contents:
            if not content.tool_call:
                continue

            tool_call = content.tool_call
            tool = self.context.get_tool(tool_call.name)

            # Push tool execution start event
            stream.push(
                AgentEvent(
                    "tool_execution_start",
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    args=tool_call.arguments,
                )
            )

            is_error = False
            try:
                if not tool:
                    raise ValueError(f"Tool {tool_call.name} not found")

                # Validate arguments
                validated_args = tool.validate_args(tool_call.arguments)

                # Execute tool
                result = await tool.execute(tool_call.id, validated_args)

                if not isinstance(result, ToolResult):
                    result = ToolResult.text(str(result))

            except Exception as e:
                result = ToolResult.error(str(e))
                is_error = True
                logger.error(f"Tool execution failed: {e}")

            # Push tool execution end event
            stream.push(
                AgentEvent(
                    "tool_execution_end",
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    result=result,
                    is_error=is_error,
                )
            )

            # Create tool result message
            result_msg = AgentMessage(
                role="toolResult",
                content=result.content,
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                is_error=is_error,
                details=result.details,
            )

            results.append(result_msg)
            stream.push(AgentEvent("message_start", message=result_msg))
            stream.push(AgentEvent("message_end", message=result_msg))

        return results


# ============================================================================
# Convenience Functions
# ============================================================================


def create_user_message(text: str) -> AgentMessage:
    """Create a user message."""
    return AgentMessage(
        role="user", content=[MessageContent(type=MessageType.TEXT, text=text)]
    )


def create_system_message(text: str) -> AgentMessage:
    """Create a system message."""
    return AgentMessage(
        role="system", content=[MessageContent(type=MessageType.TEXT, text=text)]
    )


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    # Example of creating an agent
    print("Agent Core module loaded successfully")
    print("Use AgentCore with your LLM client to run the agent loop")
