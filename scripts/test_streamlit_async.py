import nest_asyncio
nest_asyncio.apply()

import streamlit as st
import asyncio
import sys
sys.path.insert(0, ".")

st.title("Async + Streaming Test")
st.caption("Tests that asyncio works correctly in Streamlit")


async def fake_agent_stream(message: str):
    """Simulates what the real agent does."""
    yield f"Processing: {message}\n"
    await asyncio.sleep(0.1)
    yield "[TOOL_START:search_restaurants]"
    await asyncio.sleep(0.3)
    yield "[TOOL_END:search_restaurants]"
    await asyncio.sleep(0.1)
    words = "Here are the best Italian restaurants for you.".split()
    for word in words:
        yield word + " "
        await asyncio.sleep(0.05)


# Test 1: Basic asyncio.run works
if st.button("Test 1: asyncio.run()"):
    async def simple():
        await asyncio.sleep(0.1)
        return "asyncio works"
    result = asyncio.run(simple())
    st.success(f"Result: {result}")

# Test 2: asyncio.run() twice in same session
if st.button("Test 2: asyncio.run() twice"):
    async def task1():
        await asyncio.sleep(0.05)
        return "first"
    async def task2():
        await asyncio.sleep(0.05)
        return "second"
    r1 = asyncio.run(task1())
    r2 = asyncio.run(task2())
    st.success(f"Both worked: {r1}, {r2}")

# Test 3: Streaming simulation
if st.button("Test 3: Streaming response"):
    placeholder = st.empty()
    tool_status = st.empty()

    # Use a mutable container to avoid nonlocal scope issues
    state = {"full_text": ""}

    async def run_stream():
        async for token in fake_agent_stream("test"):
            if token.startswith("[TOOL_START:"):
                tool_name = token[12:-1]
                tool_status.info(f"Calling {tool_name}...")
            elif token.startswith("[TOOL_END:"):
                tool_status.empty()
            else:
                state["full_text"] += token
                placeholder.markdown(state["full_text"] + "...")

    asyncio.run(run_stream())
    placeholder.markdown(state["full_text"])
    st.success("Streaming complete!")

st.divider()
st.info(
    "All 3 tests must pass before building "
    "the main frontend."
)
