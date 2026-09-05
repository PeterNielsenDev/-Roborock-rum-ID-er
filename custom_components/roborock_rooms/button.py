"""Button platform for Roborock Rooms.

Creates one "Clean" button per room, so a single room can be cleaned from a
dashboard without remembering its segment id.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import _async_clean_rooms
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
                    new_entities.append(RoborockRoomCleanButton(coordinator, duid, room.segment_id))
        if new_entities:
            async_add_entities(new_entities)

    _add_new_rooms()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_rooms))


class RoborockRoomCleanButton(RoborockRoomEntity, ButtonEntity):
    """Starts a segment clean for a single room."""

    _attr_icon = "mdi:broom"

    def __init__(self, coordinator: RoborockRoomsCoordinator, duid: str, segment_id: int) -> None:
        super().__init__(coordinator, duid, segment_id)
        self._attr_unique_id = f"{duid}_{segment_id}_clean"

    @property
    def name(self) -> str | None:
        room = self._room
        return f"Clean {room.name}" if room else None

    async def async_press(self) -> None:
        await _async_clean_rooms(self.hass, self._duid, [self._segment_id], repeat=1)
