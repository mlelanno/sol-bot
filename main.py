import json
from core.state import TokenState
from agents.bot1_scout import run_scout
from agents.bot2_news import run_news
from agents.bot3_sentiment import run_sentiment
from agents.bot4_charts import run_charts
from agents.bot5_risk import run_risk
from agents.bot6_decision import run_decision

def run_pipeline(token_address: str, ticker: str = "") -> TokenState:
    # 1. Initialisation de l'état
    state = TokenState(token_address=token_address, ticker=ticker)

    # 2. Chaînage séquentiel des 6 agents
    state = run_scout(state)
    state = run_news(state)
    state = run_sentiment(state)
    state = run_charts(state)
    state = run_risk(state)
    state = run_decision(state)

    return state

if __name__ == "__main__":
    dummy_token = "So11111111111111111111111111111111111111112"
    result = run_pipeline(dummy_token, ticker="TEST")
    print(json.dumps(result.model_dump(), indent=2))
