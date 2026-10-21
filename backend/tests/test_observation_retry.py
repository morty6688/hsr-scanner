import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.core.observation_retry import DetectionIncomplete, retry_observation


class RetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_detection_recovers(self):
        observe = AsyncMock(side_effect=[DetectionIncomplete('missing'), ('relic', b'image')])
        with patch('app.core.observation_retry.asyncio.sleep', new_callable=AsyncMock):
            result = await retry_observation(observe, Mock(), lambda: False)
        self.assertEqual(result, ('relic', b'image'))
        self.assertEqual(observe.await_count, 2)

    async def test_persistent_detection_is_bounded(self):
        observe = AsyncMock(side_effect=DetectionIncomplete('missing'))
        with patch('app.core.observation_retry.asyncio.sleep', new_callable=AsyncMock):
            with self.assertRaises(DetectionIncomplete):
                await retry_observation(observe, Mock(), lambda: False)
        self.assertEqual(observe.await_count, 3)

    async def test_stop_prevents_retry(self):
        observe = AsyncMock(side_effect=DetectionIncomplete('missing'))
        with self.assertRaises(InterruptedError):
            await retry_observation(observe, Mock(), Mock(side_effect=[False, True]))
        self.assertEqual(observe.await_count, 1)

    async def test_focus_loss_prevents_observation(self):
        observe = AsyncMock()
        with self.assertRaises(InterruptedError):
            await retry_observation(observe, Mock(side_effect=InterruptedError('focus')), lambda: False)
        observe.assert_not_awaited()
