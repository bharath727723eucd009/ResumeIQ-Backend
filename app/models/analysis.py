from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class SkillGap(BaseModel):
    skill: str
    importance: str
    learn_url: Optional[str] = None

class Suggestion(BaseModel):
    section: str
    original: str
    improved: str
    reason: str

class KeywordMatch(BaseModel):
    keyword: str
    found: bool
    frequency: int
    importance: float
