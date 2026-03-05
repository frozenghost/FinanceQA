# Research Skill Guidelines

## When to Use

### search_knowledge_base
- User asks about financial concepts, definitions, terminology
- User wants to understand metrics, ratios, or formulas
- User inquires about general financial knowledge
- Information is likely to be in educational/reference materials

### search_web
- User asks about very recent events or news
- User wants latest information not in knowledge base
- User inquires about breaking news or announcements
- Knowledge base search returns no results

## Best Practices

### For Knowledge Base Search
- Rephrase user question into clear search query
- If no results found, explicitly tell user and suggest web search
- Never fabricate information if knowledge base has no answer
- Cite sources from metadata when presenting information

### For Web Search
- Use specific, targeted search queries
- Combine multiple search results for comprehensive answer
- Always include source URLs for verification
- Mention that information is from web search (not knowledge base)

## Search Strategy
1. Try knowledge base first for conceptual questions
2. Use web search for time-sensitive or recent information
3. If knowledge base fails, automatically suggest web search
4. Combine both sources when appropriate for comprehensive answers

## Anti-Hallucination Rules
- NEVER make up information if search returns no results
- ALWAYS cite sources for factual claims
- If uncertain, explicitly state "I don't have information about..."
- Recommend web search or other tools when knowledge base is insufficient
