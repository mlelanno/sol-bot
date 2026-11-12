from core.state import TokenState, DecisionReport
from core.llm import query_qwen

DECISION_SYSTEM_PROMPT = """Tu es le Bot 6 (Decision Arbiter) d'une salle des marchés de memecoins.
Tu reçois l'état consolidé des 5 autres agents (Scout, News, Sentiment, Charts, Risk).
Tu dois rendre un verdict ferme parmi :
- "BUY" : Les indicateurs convergent, liquidité suffisante, risque maîtrisé.
- "WAIT" : Signaux mitigés ou attente d'un meilleur point d'entrée.
- "SKIP" : Anomalie détectée, risque élevé ou absence d'intérêt.

Réponds STRICTEMENT au format JSON avec cette structure :
{
  "action": "BUY" | "WAIT" | "SKIP",
  "confidence": <entier entre 0 et 100>,
  "reasoning": "<explication concise en 1 ou 2 phrases>"
}"""

def run_decision(state: TokenState) -> TokenState:
    # 1. Règle stricte : si le Risk Manager a mis son veto, rejet immédiat sans calcul IA
    if state.risk.veto:
        state.decision = DecisionReport(
            action="SKIP",
            confidence=100,
            reasoning=f"Veto du Bot Risk : {state.risk.reason}"
        )
        return state

    # 2. Construction de la synthèse pour le LLM
    prompt = f"""Analyse ce token et rends ta décision finale :
- Ticker: {state.ticker} ({state.token_address})
- Scout: Volume surge={state.scout.volume_surge}, Liq=${state.scout.liquidity_usd}, Top10={state.scout.top10_percentage}%
- News: Catalyseur={state.news.catalyst_found} ({state.news.event_type})
- Sentiment: Score={state.sentiment.sentiment_score}/100, Hype={state.sentiment.hype_level}, Bots={state.sentiment.bot_farm_suspected}
- Charts: Tendance={state.charts.trend}, Entrée={state.charts.entry_target}, Stop={state.charts.stop_loss}
- Risk: Score={state.risk.risk_score}/10, Allocation={state.risk.suggested_position_sol} SOL

Réponds en JSON strict."""

    # 3. Inférence sur la RX 6800
    res = query_qwen(prompt=prompt, system_prompt=DECISION_SYSTEM_PROMPT, force_json=True)

    state.decision = DecisionReport(
        action=res.get("action", "WAIT"),
        confidence=res.get("confidence", 0),
        reasoning=res.get("reasoning", "Erreur de formatage du modèle.")
    )
    return state
