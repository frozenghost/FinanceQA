"""
Simple test to verify the agent outputs knowledge base content faithfully.
Run this script and compare the output with the Wikipedia article.
"""

import asyncio
import sys
import io
from pathlib import Path

# Fix encoding for Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.agent.graph_with_coordinator import get_agent_with_coordinator


async def test_agent_output():
    """Test agent output against Wikipedia article."""
    
    agent = get_agent_with_coordinator()
    
    # Test question
    question = "什么是市盈率"
    
    print("=" * 70)
    print(f"Question: {question}")
    print("=" * 70)
    print("\nReference: https://zh.wikipedia.org/wiki/%E5%B8%82%E7%9B%88%E7%8E%87")
    print("=" * 70)
    
    config = {"configurable": {"thread_id": "test-001"}}
    
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": question}]},
        config
    )
    
    print("\n=== AGENT RESPONSE ===\n")
    
    # Find all assistant messages and their content
    for i, msg in enumerate(result.get("messages", [])):
        msg_type = type(msg).__name__
        if hasattr(msg, "content") and msg.content:
            content = msg.content
            print(f"\n--- Message {i}: {msg_type} (len={len(content)}) ---")
            # Print full content for assistant messages
            if msg_type == "AIMessage":
                print(content)
            else:
                print(content[:200] + "..." if len(content) > 200 else content)
    
    print("\n" + "=" * 70)
    print("COMPARISON CHECK:")
    print("=" * 70)
    print("""
Please verify the response against the Wikipedia article:
1. Does it contain the full definition (市盈率定义)?
2. Does it include the formula (市盈率 = 每股市价 / 每股盈余)?
3. Are there any phrases like "Based on..." or "以下是..."?
4. Is the content complete or summarized?
5. Are there any parts missing compared to the original article?
""")


if __name__ == "__main__":
    asyncio.run(test_agent_output())
