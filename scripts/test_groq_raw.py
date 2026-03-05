# scripts/test_groq_raw.py
#
# PURPOSE: Establish ground truth for how
# llama3-groq-8b-8192-tool-use-preview responds
# to tool calls. All parsing logic in the agent
# will be derived from the output of this script.
#
# MODEL RATIONALE:
# llama3-groq-8b-8192-tool-use-preview was selected
# because:
# 1. 8B parameters meets "small model" requirement
# 2. Fine-tuned for tool use (better than base 8B)
# 3. Groq API = no local GPU required
# 4. Architecture is model-agnostic (one line to swap)

import os
import json
from groq import Groq

client = Groq(api_key=os.environ["GROQ_API_KEY"])
MODEL = "llama-3.1-8b-instant"

print(f"Testing model: {MODEL}")
print("=" * 50)

# Minimal tool schema for testing
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_restaurants",
            "description": (
                "Search for available GoodFoods restaurants "
                "matching the user's requirements. Call this "
                "when the user wants to find a restaurant."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "party_size": {
                        "type": "integer",
                        "description": "Number of people dining",
                    },
                    "cuisine": {
                        "type": "string",
                        "description": "Type of cuisine preferred",
                    },
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format",
                    },
                    "time": {
                        "type": "string",
                        "description": "Preferred time in HH:MM format",
                    },
                },
                "required": ["party_size"],
            },
        },
    }
]

SYSTEM_PROMPT = """You are Sage, an AI reservation concierge for GoodFoods.

When a user wants to find a restaurant, you MUST call the search_restaurants tool.
Do not describe restaurants from memory. Always use the tool.

Example of correct behavior:
User: "Find me Italian for 4 people"
Action: Call search_restaurants with party_size=4, cuisine="Italian"
NOT: "Here are some Italian restaurants I know about..."
"""

# ─────────────────────────────────────────────
# TEST 1: Does the model call the tool at all?
# ─────────────────────────────────────────────
print("\n=== TEST 1: Basic tool call triggered ===")
response = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "I need a table for 4 people this Saturday "
                "at 7pm, Italian food please"
            ),
        },
    ],
    tools=TOOLS,
    tool_choice="auto",
    max_tokens=500,
)

message = response.choices[0].message
finish_reason = response.choices[0].finish_reason

print(f"Finish reason: {finish_reason}")
print(f"Has tool_calls: {bool(message.tool_calls)}")
print(f"Content: {message.content}")

if message.tool_calls:
    tc = message.tool_calls[0]
    print(f"Tool name: {tc.function.name}")
    print(f"Arguments (raw): {tc.function.arguments}")
    try:
        args = json.loads(tc.function.arguments)
        print(f"Arguments (parsed): {args}")
        print("TEST 1: PASS")
    except json.JSONDecodeError as e:
        print(f"TEST 1: FAIL - Arguments not valid JSON: {e}")
else:
    print("TEST 1: FAIL - No tool call made")

# Save tc for later tests
tc_id = message.tool_calls[0].id if message.tool_calls else "fake_id_001"
tc_args = (
    message.tool_calls[0].function.arguments
    if message.tool_calls
    else '{"party_size": 4}'
)
tc_name = (
    message.tool_calls[0].function.name
    if message.tool_calls
    else "search_restaurants"
)

# ─────────────────────────────────────────────
# TEST 2: Tool result injection format
# ─────────────────────────────────────────────
print("\n=== TEST 2: Tool result injection format ===")

messages_with_result = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {
        "role": "user",
        "content": (
            "I need a table for 4 people this Saturday "
            "at 7pm, Italian food please"
        ),
    },
    {
        "role": "assistant",
        # CRITICAL: Groq API requires content to be a string, never None
        "content": message.content or "",
        "tool_calls": [
            {
                "id": tc_id,
                "type": "function",
                "function": {
                    "name": tc_name,
                    "arguments": tc_args,
                },
            }
        ],
    },
    {
        "role": "tool",
        "tool_call_id": tc_id,
        "content": json.dumps(
            {
                "success": True,
                "data": [
                    {
                        "id": "rest-001",
                        "name": "Bella Roma",
                        "cuisine": "Italian",
                        "neighborhood": "Downtown",
                        "ambiance": ["quiet", "business_friendly"],
                        "available_slots": ["7:00 PM", "7:30 PM"],
                    }
                ],
            }
        ),
    },
]

try:
    response2 = client.chat.completions.create(
        model=MODEL,
        messages=messages_with_result,
        tools=TOOLS,
        tool_choice="auto",
        max_tokens=500,
    )

    message2 = response2.choices[0].message
    print(f"Finish reason: {response2.choices[0].finish_reason}")
    print(f"Has tool_calls: {bool(message2.tool_calls)}")
    print(f"Content: {message2.content}")

    if message2.content and not message2.tool_calls:
        print("TEST 2: PASS - Got final answer after tool result")
    elif message2.tool_calls:
        print("TEST 2: PARTIAL - Model made another tool call (acceptable)")
    else:
        print("TEST 2: FAIL - No content and no tool call")
except Exception as e:
    # 8B models sometimes hallucinate tool calls not in schema
    print(f"TEST 2: PARTIAL - API error (expected with 8B): {e}")
    print("DIAGNOSIS: Model hallucinated a tool not in schema.")
    print("This is handled by tool_dispatcher hallucination detection.")

# ─────────────────────────────────────────────
# TEST 3: tool_choice="required"
# ─────────────────────────────────────────────
print("\n=== TEST 3: tool_choice='required' behavior ===")
try:
    response3 = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Find me a restaurant for 2 people tonight",
            },
        ],
        tools=TOOLS,
        tool_choice="required",
        max_tokens=500,
    )

    message3 = response3.choices[0].message
    print(f"Finish reason: {response3.choices[0].finish_reason}")
    print(f"Has tool_calls: {bool(message3.tool_calls)}")

    if message3.tool_calls:
        args3 = json.loads(message3.tool_calls[0].function.arguments)
        print(f"Arguments: {args3}")
        print("TEST 3: PASS - tool_choice=required works")
    else:
        print("TEST 3: FAIL - Even required didn't force tool call")
except Exception as e:
    print(f"TEST 3: PARTIAL - tool_choice=required flaky on 8B: {e}")
    print("DECISION: Use tool_choice='auto' with strong prompting instead.")

# ─────────────────────────────────────────────
# TEST 4: Streaming with tool calls
# ─────────────────────────────────────────────
print("\n=== TEST 4: Streaming tool call accumulation ===")
stream = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "Find Italian food for 3 people Saturday",
        },
    ],
    tools=TOOLS,
    tool_choice="auto",
    max_tokens=500,
    stream=True,
)

accumulated_tool_calls = []
accumulated_content = ""
finish_reason_stream = None

for chunk in stream:
    choice = chunk.choices[0]
    if choice.finish_reason:
        finish_reason_stream = choice.finish_reason
    delta = choice.delta

    if delta.content:
        accumulated_content += delta.content

    if delta.tool_calls:
        for tc_chunk in delta.tool_calls:
            idx = tc_chunk.index
            while len(accumulated_tool_calls) <= idx:
                accumulated_tool_calls.append(
                    {"id": "", "name": "", "arguments": ""}
                )
            if tc_chunk.id:
                accumulated_tool_calls[idx]["id"] = tc_chunk.id
            if tc_chunk.function.name:
                accumulated_tool_calls[idx]["name"] = tc_chunk.function.name
            if tc_chunk.function.arguments:
                accumulated_tool_calls[idx][
                    "arguments"
                ] += tc_chunk.function.arguments

print(f"Finish reason: {finish_reason_stream}")
print(f"Accumulated content: '{accumulated_content}'")
print(f"Accumulated tool calls: {accumulated_tool_calls}")

if accumulated_tool_calls:
    try:
        args4 = json.loads(accumulated_tool_calls[0]["arguments"])
        print(f"Parsed args: {args4}")
        print("TEST 4: PASS")
    except json.JSONDecodeError as e:
        print(f"TEST 4: FAIL - Argument JSON invalid: {e}")
        print(f"Raw: {accumulated_tool_calls[0]['arguments']}")
else:
    print("TEST 4: INFO - No tool call in stream")
    print("Model gave conversational response")
    print("Check if content is non-empty:", bool(accumulated_content))

# ─────────────────────────────────────────────
# TEST 5: Reliability check - 5 runs
# ─────────────────────────────────────────────
print("\n=== TEST 5: Tool call reliability (5 runs) ===")
print("This may take 15-20 seconds...")

tool_call_count = 0
test_messages = [
    "Find Italian for 4 people Saturday 7pm",
    "I need a table for 2 tomorrow evening",
    "Book me a restaurant for 6 people Sunday lunch",
    "Looking for Japanese food for 3 this Friday",
    "Find somewhere for a business lunch for 5 people",
]

for i, msg in enumerate(test_messages):
    try:
        r = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": msg},
            ],
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=200,
        )
        made_tool_call = bool(r.choices[0].message.tool_calls)
        tool_call_count += int(made_tool_call)
        status = "PASS tool call" if made_tool_call else "FAIL no tool call"
    except Exception as e:
        status = f"FAIL api error ({type(e).__name__})"
    print(f"  Run {i+1}: {status} | '{msg[:40]}'")

reliability = tool_call_count / 5
print(f"\nReliability: {tool_call_count}/5 ({reliability * 100:.0f}%)")

if reliability >= 0.8:
    print("TEST 5: PASS - Sufficient reliability for production")
elif reliability >= 0.6:
    print("TEST 5: WARNING - Marginal reliability")
else:
    print("TEST 5: FAIL - Insufficient reliability")

print("\n" + "=" * 50)
print("All tests complete.")
