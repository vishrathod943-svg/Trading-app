"""Load a validated JSON strategy at startup; never execute rule text as code."""
import json
import os
from pathlib import Path
from pydantic import BaseModel, Field, model_validator
from .analysis import DEFAULT_RULES

class Weights(BaseModel):
    setup: float = Field(30, ge=0, le=100)
    volume: float = Field(20, ge=0, le=100)
    moves: float = Field(15, ge=0, le=100)
    backtest: float = Field(20, ge=0, le=100)
    fundamentals: float = Field(15, ge=0, le=100)
    @model_validator(mode='after')
    def total(self):
        if abs(sum(self.model_dump().values())-100)>.001: raise ValueError('Weights must sum to 100')
        return self
class Rules(BaseModel):
    min_score: float = Field(65, ge=0, le=100)
    volume_ratio: float = Field(1.5, gt=0, le=100)
    bullish_rsi_min: float = Field(50, ge=0, le=100)
    bullish_rsi_max: float = Field(75, ge=0, le=100)
    bearish_rsi_min: float = Field(25, ge=0, le=100)
    bearish_rsi_max: float = Field(50, ge=0, le=100)
    weights: Weights = Field(default_factory=Weights)
    @model_validator(mode='after')
    def bounds(self):
        if self.bullish_rsi_min>=self.bullish_rsi_max or self.bearish_rsi_min>=self.bearish_rsi_max: raise ValueError('RSI lower bound must be below upper bound')
        return self

def load_rules():
    path=os.getenv('FO_RULES_FILE')
    return Rules.model_validate(json.loads(Path(path).read_text()) if path else DEFAULT_RULES).model_dump()
