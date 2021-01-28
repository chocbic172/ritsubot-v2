import asyncio


class Timer:
    def __init__(self, timeout, callback, params):
        self._timeout = timeout
        self._callback = callback
        self._params = params
        self._task = asyncio.ensure_future(self._job())

    async def _job(self):
        await asyncio.sleep(self._timeout)
        await self._callback(self._params)

    def cancel(self):
        self._task.cancel()
