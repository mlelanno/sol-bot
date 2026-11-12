from core.state import TokenState, RiskReport

def run_risk(state: TokenState) -> TokenState:
    state.risk = RiskReport(
        risk_score=9,
        veto=True,
        reason="Top 10 holders détient 65% de la supply (Risque de dump massif)",
        suggested_position_sol=0.0
    )
    return state
