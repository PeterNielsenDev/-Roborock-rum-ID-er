"""Sensor platform for Roborock Rooms.

Creates one sensor per room found on each vacuum's map. The state is the
room's segment id - the value the Roborock cloud API expects when asking a
vacuum to clean a specific room.
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COORDINATORS, DOMAIN
from .coordinator import RoborockRoomsCoordinator
from .entity import RoborockRoomEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: RoborockRoomsCoordinator = hass.data[DOMAIN][DATA_COORDINATORS][entry.entry_id]
    known: set[tuple[str, int]] = set()

    @callback
    def _add_new_rooms() -> None:
        new_entities = []
        for duid, device in coordinator.data.items():
            for room in device.rooms:
                key = (duid, room.segment_id)
                if key not in known:
                    known.add(key)
                    new_entities.append(RoborockRoomSegmentSensor(coordinator, duid, room.segment_id))
        if new_entities:
            async_add_entities(new_entities)

    _add_new_rooms()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_rooms))


class RoborockRoomSegmentSensor(RoborockRoomEntity, SensorEntity):
    """Exposes a room's segment id as the entity state."""

    _attr_icon = "mdi:floor-plan"

    def __init__(self, coordinator: RoborockRoomsCoordinator, duid: str, segment_id: int) -> None:
        super().__init__(coordinator, duid, segment_id)
        self._attr_unique_id = f"{duid}_{segment_id}_segment_id"

    @property
    def name(self) -> str | None:
        room = self._room
        return room.name if room else None

    @property
    def native_value(self) -> int | None:
        room = self._room
        return room.segment_id if room else None

    @property
    def extra_state_attributes(self) -> dict:
        room = self._room
        device = self._device
        if room is None or device is None:
            return {}
        return {
            "duid": device.duid,
            "device_name": device.name,
            "map_name": room.map_name,
            "map_flag": room.map_flag,
        }
