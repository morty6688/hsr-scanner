from typing import List

from pydantic import BaseModel


class RelicScoreResponse(BaseModel):
    score: float
    potential: float = 0
    characters: List[str]
    type: str
