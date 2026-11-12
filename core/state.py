from pydantic import BaseModel, Field
from typing import Optional, Literal

class ScoutReport(BaseModel):
    volume_surge: bool = False
    liquidity_usd: float = 0.0
    holders_count: int = 0
    top10_percentage: float = 0.0

class NewsReport(BaseModel):
    catalyst_found: bool = False
    headline: Optional[str] = None
    event_type: Literal["listing", "dev_update", "partnership", "none"] = "none"

class SentimentReport(BaseModel):
    sentiment_score: int = Field(ge=0, le=100, default=50)
    hype_level: Literal["low", "medium", "high", "organic"] = "low"
    bot_farm_suspected: bool = False

class ChartReport(BaseModel):
    trend: Literal["bullish", "bearish", "neutral"] = "neutral"
    entry_target: float = 0.0
    stop_loss: float = 0.0

class RiskReport(BaseModel):
    risk_score: int = Field(ge=1, le=10, default=5)
    veto: bool = False
    reason: str = ""
    suggested_position_sol: float = 0.0

class DecisionReport(BaseModel):
    action: Literal["BUY", "WAIT", "SKIP"] = "WAIT"
    confidence: int = Field(ge=0, le=100, default=0)
    reasoning: str = ""

class TokenState(BaseModel):
    token_address: str
    ticker: str = ""
    scout: ScoutReport = Field(default_factory=ScoutReport)
    news: NewsReport = Field(default_factory=NewsReport)
    sentiment: SentimentReport = Field(default_factory=SentimentReport)
    charts: ChartReport = Field(default_factory=ChartReport)
    risk: RiskReport = Field(default_factory=RiskReport)
    decision: DecisionReport = Field(default_factory=DecisionReport)
