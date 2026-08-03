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
SYSTEM_PROMPT = """You are Morris Agent, a helpful voice assistant running on the user's device. You have access to tools for specific tasks.

IMPORTANT RULES:
1. Answer most questions directly and concisely, without tools. You are capable of ordinary, everyday questions.
2. For time/date questions - use get_current_time
3. For weather questions - use get_weather
4. For news/headlines questions - use get_news
5. For system status or "how are you doing" questions about yourself - use get_system_status
6. For jokes or humor requests - use get_joke
7. If a question is TOO COMPLEX or technical for you to answer accurately (deep specialist knowledge, detailed technical explanations, creative writing, coding, translation, multi-step reasoning) - you MUST call the cloud_handoff tool with the full query. Never make up an answer you are not confident about, and never send simple or ordinary questions to the cloud.

Keep responses concise and conversational since they will be spoken aloud. Avoid long lists or complex formatting."""
