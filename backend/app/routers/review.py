from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.desktop_adapter import DesktopAdapter
from app.core.managers.global_state_manager import GlobalStateManager
from app.core.orm_models.rating_template_orm import RatingTemplateORM
from app.core.orm_models.rating_rule_orm import RatingRuleORM
from app.core.utils.formatter import Formatter
from app.core.scan_session import ScanSession, public_session

router = APIRouter(prefix='/review', tags=['Local review'])


def current_rules():
    template = RatingTemplateORM.select().where(RatingTemplateORM.in_use == True).first()
    if template is None:
        return {}
    rules = Formatter().format_rating_template(RatingRuleORM.select().where(RatingRuleORM.template_id == template.id))
    return {key: [r.model_dump() for r in value] for key, value in rules.items()}


session = ScanSession(DesktopAdapter(), current_rules)


class Threshold(BaseModel):
    threshold: float = Field(gt=0, le=1)


class Execute(BaseModel):
    session_id: str
    selected: List[str]


@router.get('')
def status():
    return public_session(session.current)


@router.post('/scan')
async def scan():
    try:
        return session.start_scan()
    except ValueError as error:
        raise HTTPException(409, str(error))


@router.post('/stop')
async def stop():
    session.request_stop()
    return {'status': 'stopping'}


@router.post('/reprice')
async def reprice(request: Threshold):
    try:
        return session.reprice(request.threshold)
    except ValueError as error:
        raise HTTPException(409, str(error))


@router.post('/execute')
async def execute(request: Execute):
    try:
        return session.start_execute(request.session_id, request.selected)
    except ValueError as error:
        raise HTTPException(409, str(error))


@router.get('/image/{name}')
def image(name: str, thumbnail: bool = False):
    if not session.current or name not in {r['screenshot'] for r in session.current['records']}:
        raise HTTPException(404)
    original = session.directory / name
    if thumbnail:
        from app.core.preview_image import thumbnail_file
        if not original.is_file():
            raise HTTPException(404)
        return FileResponse(thumbnail_file(original), media_type='image/jpeg')
    return FileResponse(original, media_type='image/png')
