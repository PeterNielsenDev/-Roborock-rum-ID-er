"""Number platform for Roborock Rooms: how many times to clean each room."""

from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import _room_settings
from .const import DATA_COORDINATORS, DOMAIN
from .coordinator import RoborockRoomsCoordinator
from .entity import RoborockRoomEntity
from .settings import MAX_REPEAT, MIN_REPEAT


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
                    new_entities.append(RoborockRoomRepeatNumber(coordinator, duid, room.segment_id))
        if new_entities:
            async_add_entities(new_entities)

    _add_new_rooms()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_rooms))


class RoborockRoomRepeatNumber(RoborockRoomEntity, RestoreNumber):
    """Number of passes (1-3) used when cleaning a single room."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:repeat"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = MIN_REPEAT
    _attr_native_max_value = MAX_REPEAT
    _attr_native_step = 1

    def __init__(self, coordinator: RoborockRoomsCoordinator, duid: str, segment_id: int) -> None:
        super().__init__(coordinator, duid, segment_id)
        self._attr_unique_id = f"{duid}_{segment_id}_repeat"

    @property
    def name(self) -> str | None:
        room = self._room
        return f"{room.name} repeat" if room else None

    @property
    def native_value(self) -> float:
        return _room_settings(self.hass).get(self._duid, self._segment_id).repeat

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._store_repeat(last.native_value)

    async def async_set_native_value(self, value: float) -> None:
        self._store_repeat(value)
        self.async_write_ha_state()

    def _store_repeat(self, value: float) -> None:
        repeat = min(MAX_REPEAT, max(MIN_REPEAT, int(value)))
        _room_settings(self.hass).update(self._duid, self._segment_id, repeat=repeat)
