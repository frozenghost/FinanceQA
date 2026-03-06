# News Skill Guidelines

## When to Use
- User asks about recent news for a company or sector
- User wants to know about market events or announcements
- User inquires about latest developments or updates

## Best Practices
- Summarize key points from multiple articles
- Provide publication dates to show recency
- Include source names for credibility
- **Always include article URLs** when presenting news (each news item should have a clickable link so users can read the full article)
- Link related news to market movements when relevant

## Query Optimization
- Use specific company names or ticker symbols
- Include relevant keywords (earnings, merger, lawsuit, etc.)
- Adjust page_size based on how much detail user wants

## Important Notes
- Results are sorted by publication date (most recent first)
- Some articles may have limited descriptions
- Always cite sources when presenting news information (use publisher/site name, not API or provider names)
- **For every news item you mention, you must include its link.** Use the `link` field from each article (it is already in Markdown form [title](url)); paste it for each item so that all 5 (or N) items have a clickable link—do not skip any
- Describe data origin in broad terms (e.g. "news search", "web news"); do not mention specific APIs or services
