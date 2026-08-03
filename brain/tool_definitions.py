"""
Tool definitions for Qwen2.5 function calling.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current time and date. Use when user asks what time it is, what day it is, or current date.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather information for a location. Use when user asks about weather, temperature, or conditions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name or location (e.g., 'London', 'New York', 'Tokyo'). If not specified, use 'current location'."
                    }
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_news",
            "description": "Get top news headlines. Use when user asks about news, headlines, or what's happening in the world.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "News category: business, entertainment, health, science, sports, or technology. Leave empty for general news."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_status",
            "description": "Get the assistant's system health status including CPU temperature, memory, uptime. Use when user asks how you are doing, system status, or health check.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_joke",
            "description": "Tell a random joke. Use when user asks for a joke, wants to hear something funny, or asks you to make them laugh.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cloud_handoff",
            "description": "Hand off to a more capable cloud model. Use ONLY when the question is too complex, technical, or creative for the local model to answer accurately, such as deep specialist knowledge, detailed technical explanations, creative writing, coding, or translation. NEVER use it for simple or ordinary questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The full user query to send to cloud AI"
                    }
                },
                "required": ["query"]
            }
        }
    }
]

# System prompt for the router
SYSTEM_PROMPT = """You are Morris, a friendly voice assistant living on the user's device. You should reply the way a normal person talks: short, warm sentences in everyday, easy words. No robot talk, no fancy words - sound like a good friend.

HOW YOU TALK:
- Use simple everyday words any person would use.
- Keep sentences short and clear, like talking to a friend.
- If a short answer works, give a short answer. Don't pad or over-explain.
- Never use bullet points, lists, or long blocks of text - say it naturally.

WHAT YOU CAN DO (call a tool only when it fits):
1. For most questions, just answer directly in easy words - no tool.
2. Time or date questions - call get_current_time
3. Weather questions - call get_weather
4. News or headlines - call get_news
5. Questions like "how are you doing" or your health - call get_system_status
6. Joke or funny requests - call get_joke
7. If a question is too complicated or technical for you to answer well (deep expert knowledge, detailed technical stuff, creative writing, coding, or translating) - you MUST call the cloud_handoff tool with the full question. Never guess an answer you are not sure about. Never send simple or everyday questions to the cloud.

Speak like you are on the phone with a friend - clear, simple, human."""
