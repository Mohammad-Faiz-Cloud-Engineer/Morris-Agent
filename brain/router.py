"""
Main routing logic - single LLM for routing and chat.
Includes text-based tool detection fallback for smaller models.
"""

import re
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from .ollama_client import OllamaClient
from .tool_definitions import TOOLS, SYSTEM_PROMPT


class ToolType(Enum):
    TIME = "get_current_time"
    WEATHER = "get_weather"
    NEWS = "get_news"
    SYSTEM_STATUS = "get_system_status"
    JOKE = "get_joke"
    CLOUD = "cloud_handoff"
    NONE = "none"  # Direct chat response


@dataclass
class RouterResult:
    """Result from the router."""
    tool: ToolType
    response: Optional[str]  # Direct response if no tool
    arguments: dict  # Tool arguments if tool called


class Router:
    """Routes user queries to appropriate handlers."""

    # Keywords for text-based tool detection (using word boundary matching)
    TIME_PHRASES = ["what time", "what's the time", "current time", "what day is it", "what's the date", "what date"]
    WEATHER_PHRASES = ["weather in", "weather for", "what's the weather", "how's the weather", "temperature in", "weather now", "weather today"]
    NEWS_PHRASES = ["news", "headlines", "what's happening", "whats happening", "current events", "top stories"]
    SYSTEM_PHRASES = ["system status", "how are you doing", "how are you feeling", "your temperature", "cpu temp", "health check", "how's your health", "how you doing"]
    JOKE_PHRASES = ["tell me a joke", "joke", "make me laugh", "something funny", "say something funny"]

    # Phrases that the local model can handle — simple chat, greetings, identity
    LOCAL_PHRASES = [
        "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
        "how are you", "what's up", "who are you", "what are you", "what's your name",
        "thank you", "thanks", "bye", "goodbye", "see you", "good night",
        "help", "what can you do",
    ]

    # Rolling context summarization. Instead of replaying the entire raw
    # transcript on every turn (which grows prompt length and VRAM use without
    # bound on long conversations), the oldest exchanges are folded into a
    # compact summary and only the most recent few exchanges are kept in full.
    MAX_RAW_EXCHANGES = 4
    MAX_SUMMARY_CHARS = 2000
    SUMMARY_PROMPT = (
        "You are the summarizer for a conversation with a voice assistant. "
        "Compress it into 2-3 plain sentences, keeping important facts: names, "
        "places, times, temperatures, numbers, decisions, and the assistant's "
        "final statements. Blend it with any existing summary so the result "
        "covers everything so far in one continuous text. Output only the "
        "summary, no preamble and no bullet points."
    )

    def __init__(self, ollama_client: OllamaClient):
        self.client = ollama_client
        self.conversation_history = []
        self.summary = ""

    def _is_local_chat(self, user_input: str) -> bool:
        """Check if the input is simple enough for the local model."""
        user_lower = user_input.lower().strip()
        # A greeting/phrase only counts when it starts the input, so "hi"
        # inside "what is this" or "help" inside a complex question is never
        # mistaken for a simple chat request.
        for phrase in self.LOCAL_PHRASES:
            if user_lower.startswith(phrase):
                return True
        # Very short inputs (1-3 words) that aren't questions are likely greetings
        words = user_lower.split()
        if len(words) <= 3 and "?" not in user_input:
            return True
        return False

    def _extract_news_category(self, user_input: str) -> str:
        """Extract news category from user input."""
        user_lower = user_input.lower()
        categories = ["business", "entertainment", "health", "science", "sports", "technology"]
        # Also match common synonyms
        synonyms = {"tech": "technology", "sport": "sports", "medical": "health"}
        for synonym, category in synonyms.items():
            if synonym in user_lower:
                return category
        for cat in categories:
            if cat in user_lower:
                return cat
        return ""

    def _detect_tool_from_text(self, user_input: str, response_text: str) -> Tuple[ToolType, dict]:
        """
        Detect tool from user input keywords and/or model response text.
        Fallback for models that don't use structured tool calls.
        """
        user_lower = user_input.lower()
        response_lower = (response_text or "").lower()

        # Priority 1: Check for tool mentions in model response (e.g., "[get_current_time]")
        if "get_current_time" in response_lower:
            return ToolType.TIME, {}

        if "get_weather" in response_lower:
            location = self._extract_location(user_input, response_text)
            return ToolType.WEATHER, {"location": location}

        if "get_news" in response_lower:
            category = self._extract_news_category(user_input)
            return ToolType.NEWS, {"category": category}

        if "get_system_status" in response_lower:
            return ToolType.SYSTEM_STATUS, {}

        if "get_joke" in response_lower:
            return ToolType.JOKE, {}

        if "cloud_handoff" in response_lower:
            return ToolType.CLOUD, {"query": user_input}

        # Priority 2: Check for specific phrases in user input
        for phrase in self.TIME_PHRASES:
            if phrase in user_lower:
                return ToolType.TIME, {}

        for phrase in self.WEATHER_PHRASES:
            if phrase in user_lower:
                location = self._extract_location(user_input, "")
                return ToolType.WEATHER, {"location": location}

        for phrase in self.NEWS_PHRASES:
            if phrase in user_lower:
                category = self._extract_news_category(user_input)
                return ToolType.NEWS, {"category": category}

        for phrase in self.JOKE_PHRASES:
            if phrase in user_lower:
                return ToolType.JOKE, {}

        for phrase in self.SYSTEM_PHRASES:
            if phrase in user_lower:
                return ToolType.SYSTEM_STATUS, {}

        # Priority 3: The model produced a real answer — keep it local
        if response_text and response_text.strip():
            return ToolType.NONE, {}

        # Priority 4: If it's simple chat, keep local
        if self._is_local_chat(user_input):
            return ToolType.NONE, {}

        # Priority 5: The local model produced nothing useful (no tool call,
        # no answer) — ask the cloud so the user never gets silence.
        return ToolType.CLOUD, {"query": user_input}

    def _extract_location(self, user_input: str, response_text: str) -> str:
        """Extract location from user input or response."""
        # Try to find location in model response
        match = re.search(r'location["\s=:]+["\']*([^"\'\]\s,]+)', response_text or "", re.IGNORECASE)
        if match:
            return match.group(1)

        # Try common patterns in user input
        patterns = [
            r"weather (?:in|for|at) ([A-Za-z\s]+)",
            r"in ([A-Za-z]+)",
            r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)"  # Capitalized words
        ]

        for pattern in patterns:
            match = re.search(pattern, user_input)
            if match:
                loc = match.group(1).strip()
                # Drop trailing time words swept in by the greedy pattern
                # (e.g. "London today"), longest alternatives first.
                loc = re.sub(r"\s+(right now|today|tomorrow|tonight|now)$", "", loc, flags=re.IGNORECASE)
                # Filter out common words
                if loc.lower() not in ["the", "is", "it", "what", "how", "like"]:
                    return loc

        return ""  # No location found, orchestrator will use config default

    def route(self, user_input: str) -> RouterResult:
        """Route user input and manage rolling conversation summarization."""
        result = self._route_core(user_input)
        self._maybe_summarize()
        return result

    def _route_core(self, user_input: str) -> RouterResult:
        """
        Route user input to appropriate handler.
        """
        # Build messages
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

        # Bring back a compact summary of the older parts of the conversation
        if self.summary:
            messages.append(
                {
                    "role": "system",
                    "content": f"Earlier in this conversation:\n{self.summary}",
                }
            )

        # Add conversation history (keep the last few exchanges for context).
        # Every exchange is a (user, assistant, tool result) triplet; a tail
        # slice can cut mid-triplet, so drop any leading message whose pair
        # fell outside the window.
        history = self.conversation_history[-12:]
        while history:
            if history[0].get("role") == "tool":
                # Its assistant tool-call was cut off by the window.
                history.pop(0)
            elif (
                history[0].get("role") == "assistant"
                and history[0].get("tool_calls")
                and (len(history) < 2 or history[1].get("role") != "tool")
            ):
                # A dangling tool call: Ollama requires every assistant
                # tool call to be followed by its tool result.
                history.pop(0)
            else:
                break
        messages.extend(history)

        # Add current user message
        messages.append({"role": "user", "content": user_input})

        # Get response with tool calling
        response = self.client.chat(messages, tools=TOOLS)

        # Process response
        if response.is_tool_call:
            # Model used structured tool calling
            tool_call = response.tool_calls[0]

            try:
                tool_type = ToolType(tool_call.name)
            except ValueError:
                # Unknown tool name — fall back to text detection instead of
                # returning a silent (NONE, no response) result.
                tool_type, arguments = self._detect_tool_from_text(
                    user_input, response.content
                )
                if tool_type == ToolType.NONE:
                    self.conversation_history.append(
                        {"role": "user", "content": user_input}
                    )
                    self.conversation_history.append(
                        {"role": "assistant", "content": response.content or ""}
                    )
                    return RouterResult(
                        tool=ToolType.NONE,
                        response=response.content,
                        arguments={},
                    )
                self._record_tool_call(user_input, tool_type, arguments)
                return RouterResult(
                    tool=tool_type, response=None, arguments=arguments
                )

            self._record_tool_call(user_input, tool_type, tool_call.arguments)

            return RouterResult(
                tool=tool_type,
                response=None,
                arguments=tool_call.arguments
            )
        else:
            # Fallback: detect tool from text
            tool_type, arguments = self._detect_tool_from_text(
                user_input, response.content
            )

            if tool_type == ToolType.NONE:
                # Simple chat — use the local model's response
                self.conversation_history.append(
                    {"role": "user", "content": user_input}
                )
                self.conversation_history.append(
                    {"role": "assistant", "content": response.content or ""}
                )
                return RouterResult(
                    tool=ToolType.NONE,
                    response=response.content,
                    arguments={}
                )
            else:
                # Tool or cloud handoff
                self._record_tool_call(user_input, tool_type, arguments)
                return RouterResult(
                    tool=tool_type,
                    response=None,
                    arguments=arguments
                )

    def _record_tool_call(
        self, user_input: str, tool_type: ToolType, arguments: dict
    ) -> None:
        """
        Store the user message and the assistant tool call so the tool result
        recorded afterwards is grounded in context for later turns.
        """
        self.conversation_history.append(
            {"role": "user", "content": user_input}
        )
        self.conversation_history.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": tool_type.value,
                            "arguments": arguments or {},
                        }
                    }
                ],
            }
        )

    def record_tool_result(self, result_text: str) -> None:
        """
        Store the result of the last tool call for future context.

        No-op unless the previous message is an assistant tool call, so stray
        or repeated calls can never leave an orphaned ``tool`` message.
        """
        if not self.conversation_history:
            return
        last = self.conversation_history[-1]
        tool_calls = (
            last.get("tool_calls") if last.get("role") == "assistant" else None
        )
        if not tool_calls:
            return
        tool_name = tool_calls[0].get("function", {}).get("name", "")
        message = {"role": "tool", "content": result_text or ""}
        if tool_name:
            message["tool_name"] = tool_name
        self.conversation_history.append(message)

    @staticmethod
    def _split_exchanges(history: list) -> list:
        """Split history into exchange groups, each starting with a user turn."""
        exchanges = []
        start = 0
        for index, message in enumerate(history):
            if index > 0 and message.get("role") == "user":
                exchanges.append(history[start:index])
                start = index
        exchanges.append(history[start:])
        return exchanges

    @staticmethod
    def _exchange_to_text(exchange: list) -> str:
        """Render one exchange as plain text for the summarizer."""
        lines = []
        for message in exchange:
            role = message.get("role")
            if role == "assistant" and message.get("tool_calls"):
                for call in message["tool_calls"]:
                    fn = call.get("function", {})
                    lines.append(f"assistant called {fn.get('name')} with {fn.get('arguments', {})}")
            elif role == "tool" and message.get("content"):
                lines.append(f"tool result: {message['content']}")
            elif role in ("user", "assistant") and message.get("content"):
                lines.append(f"{role}: {message['content']}")
        return " ".join(lines)

    def _summarize(self, exchanges_text: str) -> str:
        """Summarize old exchanges (together with the prior summary) with the local model."""
        try:
            response = self.client.chat(
                [
                    {"role": "system", "content": self.SUMMARY_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Existing summary: {self.summary or '(none)'}\n"
                            f"Conversation to condense: {exchanges_text}"
                        ),
                    },
                ],
                tools=None,
            )
            summary = (response.content or "").strip()
            if summary:
                return summary
        except Exception as error:
            print(f"[router] summarization failed: {error}")
        return exchanges_text[-300:] if exchanges_text else ""

    def _maybe_summarize(self) -> None:
        """Fold the oldest exchanges into the summary so context stays bounded."""
        exchanges = self._split_exchanges(self.conversation_history)
        while len(exchanges) > self.MAX_RAW_EXCHANGES:
            oldest = exchanges.pop(0)
            condensed = self._summarize(self._exchange_to_text(oldest))
            if self.summary:
                self.summary = f"{self.summary}\n{condensed}"
            else:
                self.summary = condensed
            # Hard cap so history can never grow without bound.
            self.summary = self.summary[-self.MAX_SUMMARY_CHARS:]
        if self.conversation_history and self._split_exchanges(self.conversation_history) != exchanges:
            self.conversation_history = [
                message for group in exchanges for message in group
            ]

    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history = []
        self.summary = ""
