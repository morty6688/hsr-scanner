import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from uvicorn import Server

from app.core.state_machines.pipeline_state_machine import PipelineStateMachine
from app.core.utils.database import get_pipeline_config
from app.life_span import life_span
from app.routers import config
from app.routers import files
from app.routers import rating_template
from app.routers import state
from app.routers import review

app = FastAPI(lifespan=life_span)
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=[])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1420", "http://127.0.0.1:1420", "http://tauri.localhost", "tauri://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(review.router)
app.include_router(state.router)
app.include_router(rating_template.router)
app.include_router(files.router)
app.include_router(config.router, prefix="/config", tags=["Config Operations"])
app.mount("/", socketio.ASGIApp(sio))

current_runners = {}


@sio.event
async def connect(sid, environ):
    logger.debug(f"新的ws连接: {sid}")
    pass


@sio.event
async def disconnect(sid):
    logger.debug(f"ws断开连接: {sid}")
    runner = current_runners.get(sid)
    if runner:
        await runner.handle_stop_pipeline()
        del current_runners[sid]


@sio.event
async def start_pipeline(sid, data):
    await sio.emit('pipeline_error', {'error': '旧流水线已停用，请使用本地扫描预览'}, to=sid)


@sio.event
async def stop_pipeline(sid, data):
    runner = current_runners.get(sid)
    if runner:
        await runner.handle_stop_pipeline()
        del current_runners[sid]


if __name__ == '__main__':
    config = uvicorn.Config(app, port=0)
    server: Server = uvicorn.Server(config)
    server.run()
