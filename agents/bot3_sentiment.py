from core.state import TokenState, SentimentReport

def run_sentiment(state: TokenState) -> TokenState:
    state.sentiment = SentimentReport(
        sentiment_score=82,
        hype_level="organic",
        bot_farm_suspected=False
    )
    return state
