from core.state import TokenState, ScoutReport

def run_scout(state: TokenState) -> TokenState:
    state.scout = ScoutReport(
        volume_surge=True,
        liquidity_usd=45000.0,
        holders_count=1250,
        top10_percentage=18.5
    )
    return state
