"""Bounded read-only retries: never navigate or click after a failed observation."""
import asyncio


class DetectionIncomplete(ValueError):
    pass


async def retry_observation(observe, check_focus, cancelled):
    for attempt in range(3):
        if cancelled():
            raise InterruptedError('已停止')
        check_focus()
        try:
            return await observe()
        except DetectionIncomplete:
            if cancelled():
                raise InterruptedError('已停止')
            if attempt == 2:
                raise
            await asyncio.sleep(.6)
