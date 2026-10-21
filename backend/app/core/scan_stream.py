"""One-frame lookahead; only the foreground coroutine can navigate."""
import asyncio


async def scan_stream(adapter, observe, limit=3000):
    first = await observe()
    capture = adapter.prepare_capture() if hasattr(adapter, 'prepare_capture') else None
    if capture is not None and hasattr(first[1], 'shape'):
        x, y, w, h = capture.rect
        first = first[0], first[1][y:y+h, x:x+w].copy()
    yield first
    if capture is None:
        for _ in range(1, limit):
            adapter.check_focus()
            if adapter.cancelled():
                raise InterruptedError('已停止')
            adapter.next()
            yield await observe()
        return
    if limit <= 1:
        return
    pending = None
    reading = None
    try:
        frame = await adapter.capture_next(capture)
        for index in range(1, limit):
            reading = asyncio.create_task(asyncio.wait_for(adapter.observe_frame(frame), 30))
            pending = asyncio.create_task(adapter.capture_next(capture)) if index + 1 < limit else None
            result = await reading
            reading = None
            if adapter.cancelled():
                raise InterruptedError('已停止')
            adapter.check_focus()
            yield result
            if pending is not None:
                frame = await pending
                pending = None
    finally:
        tasks = [t for t in (pending, reading) if t is not None]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
