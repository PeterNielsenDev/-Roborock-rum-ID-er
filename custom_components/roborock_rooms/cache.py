"""File-backed cache for python-roborock device/room discovery data.

Only `home_data` (the account's device/product list) is persisted across
restarts: fetching it is rate-limited by Roborock's cloud API (5/hour). Room
and segment-id discovery is deliberately NOT persisted - it's fetched live
from each vacuum over MQTT on every coordinator update (not subject to that
limiter), so newly added or renamed rooms show up immediately instead of
being hidden behind a stale cache.

The upstream `FileCache` truncates its file before serializing, so a pickling
error mid-write (some trait data holds unpicklable closures) leaves a 0-byte
file that then raises `EOFError` forever after. This writes to a temp file and
renames it into place atomically instead, and treats an unreadable/corrupt
existing file as an empty cache rather than crashing.

All actual filesystem access happens in the executor: Home Assistant's event
loop must never block on synchronous disk I/O.
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path

from homeassistant.core import HomeAssistant
from roborock.devices.cache import Cache, CacheData

_LOGGER = logging.getLogger(__name__)


def _read_cache_data(path: Path) -> CacheData:
    if path.exists() and path.stat().st_size > 0:
        try:
            return pickle.loads(path.read_bytes())
        except Exception:
            _LOGGER.warning("Discarding unreadable device cache at %s", path, exc_info=True)
    return CacheData()


def _write_cache_data(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_bytes(payload)
    tmp_path.replace(path)


class SafeFileCache(Cache):
    """Atomic, corruption-tolerant pickle file cache for a single account."""

    def __init__(self, hass: HomeAssistant, path: Path) -> None:
        self._hass = hass
        self._path = path
        self._data: CacheData | None = None

    async def get(self) -> CacheData:
        if self._data is not None:
            return self._data
        self._data = await self._hass.async_add_executor_job(_read_cache_data, self._path)
        return self._data

    async def set(self, value: CacheData) -> None:
        self._data = value

    async def flush(self) -> None:
        if self._data is None or self._data.home_data is None:
            return
        # Only home_data is persisted - see module docstring.
        persisted = CacheData(home_data=self._data.home_data)
        try:
            payload = pickle.dumps(persisted)
        except Exception:
            _LOGGER.warning("Failed to serialize device cache, leaving previous file untouched", exc_info=True)
            return
        await self._hass.async_add_executor_job(_write_cache_data, self._path, payload)
