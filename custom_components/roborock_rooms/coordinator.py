"""Data update coordinator for Roborock Rooms."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from roborock.data import UserData
from roborock.devices.device_manager import UserParams, create_device_manager
from roborock.exceptions import RoborockException

from .cache import SafeFileCache
from .const import DEFAULT_SCAN_INTERVAL_MINUTES

_LOGGER = logging.getLogger(__name__)


@dataclass
class RoborockRoom:
    """A single cleanable room/segment on a device's map."""

    segment_id: int
    name: str
    map_flag: int
    map_name: str


@dataclass
class RoborockDeviceRooms:
    """Room data for a single vacuum on the account."""

    duid: str
    name: str
    error: str | None = None
    rooms: list[RoborockRoom] = field(default_factory=list)


class RoborockRoomsCoordinator(DataUpdateCoordinator[dict[str, RoborockDeviceRooms]]):
    """Fetches the list of devices and their room/segment ids for one account."""

    def __init__(self, hass: HomeAssistant, email: str, user_data: UserData, cache_path) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"roborock_rooms ({email})",
            update_interval=timedelta(minutes=DEFAULT_SCAN_INTERVAL_MINUTES),
        )
        self.email = email
        self.user_data = user_data
        self._cache_path = cache_path

    async def _async_update_data(self) -> dict[str, RoborockDeviceRooms]:
        cache = SafeFileCache(self._cache_path)
        user_params = UserParams(username=self.email, user_data=self.user_data)
        results: dict[str, RoborockDeviceRooms] = {}
        manager = None
        try:
            manager = await create_device_manager(user_params, cache=cache)
            devices = await manager.get_devices()
            for device in devices:
                entry = RoborockDeviceRooms(duid=device.duid, name=device.name)
                results[device.duid] = entry

                if device.v1_properties is None:
                    entry.error = "not_v1_device"
                    continue

                try:
                    await device.v1_properties.status.refresh()
                    home_trait = device.v1_properties.home
                    await home_trait.discover_home()
                except RoborockException as err:
                    entry.error = str(err)
                    continue

                for map_flag, map_data in (home_trait.home_map_info or {}).items():
                    for room in sorted(map_data.rooms, key=lambda r: r.segment_id):
                        entry.rooms.append(
                            RoborockRoom(
                                segment_id=room.segment_id,
                                name=room.name or f"Room {room.segment_id}",
                                map_flag=map_flag,
                                map_name=map_data.name,
                            )
                        )
        except RoborockException as err:
            raise UpdateFailed(str(err)) from err
        finally:
            if manager is not None:
                await manager.close()
            await cache.flush()
        return results
