# Market Data Skill Guidelines

## When to Use
- User asks for current stock price, real-time quote
- User wants to see historical price movements, charts, OHLCV data
- User needs price data for a specific time period

## Tool Selection
- `get_real_time_quote`: For current price, today's performance, basic info
- `get_historical_prices`: For price history, trends, chart data

## Best Practices
- Always specify the ticker symbol clearly
- For historical data, choose appropriate period based on user's question
- Mention the 15-minute delay in data when relevant
- If user asks about multiple stocks, call the tool multiple times

## Data Limitations
- Data has ~15 minute delay (not real-time)
- Historical data availability varies by ticker
- Some tickers may not be available in Yahoo Finance
