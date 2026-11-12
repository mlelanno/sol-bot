from core.state import TokenState, ChartReport

def run_charts(state: TokenState) -> TokenState:
    state.charts = ChartReport(
        trend="bullish",
        entry_target=0.0024,
        stop_loss=0.0019
    )
    return state
