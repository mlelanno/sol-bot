from core.state import TokenState, NewsReport

def run_news(state: TokenState) -> TokenState:
    state.news = NewsReport(
        catalyst_found=True,
        headline="Annonce d'un listing CEX pour demain",
        event_type="listing"
    )
    return state
