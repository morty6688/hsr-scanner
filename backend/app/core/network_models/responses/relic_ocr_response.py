from typing import List, Optional, Any

from pydantic import BaseModel, Field

from app.core.data_models.relic_info import RelicTitle, RelicMainStat, RelicSubStat


class RelicOCRResponse(BaseModel):
    relic_title: Optional[RelicTitle] = None
    relic_main_stat: Optional[RelicMainStat] = None
    relic_sub_stat: Optional[List[RelicSubStat]] = None

    rarity: Optional[int] = None
    locked: Optional[bool] = None
    equipped: Optional[bool] = None
    discarded: Optional[bool] = None
    pending_unlock_cost: Optional[int] = None
    recognition_verified: bool = False
    ocr_path: str = 'legacy'
    ocr_device: str = 'unknown'

    raw_ocr: List[Any] = Field(default_factory=list)
    confidence: float = 0
    recognition_errors: List[str] = Field(default_factory=list)
