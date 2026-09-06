"""Button platform for Roborock Rooms.

Creates one "Clean" button per room, plus one "Clean all rooms" button per
vacuum, so rooms can be cleaned from a dashboard without remembering
segment ids.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import _async_clean_rooms, _async_execute_routine
from .const import DATA_COORDINATORS, DOMAIN
from .coordinator import RoborockRoomsCoordinator
from .entity import RoborockDeviceEntity, RoborockRoomEntity, RoborockRoutineEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: RoborockRoomsCoordinator = hass.data[DOMAIN][DATA_COORDINATORS][entry.entry_id]
    known_devices: set[str] = set()
    known_rooms: set[tuple[str, int]] = set()
    known_routines: set[tuple[str, int]] = set()

    @callback
    def _add_new_entities() -> None:
        new_entities = []
        for duid, device in coordinator.data.items():
            if duid not in known_devices:
                known_devices.add(duid)
                new_entities.append(RoborockCleanAllButton(coordinator, duid))
            for room in device.rooms:
                key = (duid, room.segment_id)
                if key not in known_rooms:
                    known_rooms.add(key)
                    new_entities.append(RoborockRoomCleanButton(coordinator, duid, room.segment_id))
            for routine in device.routines:
                key = (duid, routine.routine_id)
                if key not in known_routines:
                    known_routines.add(key)
                    new_entities.append(RoborockRoutineButton(coordinator, duid, routine.routine_id))
        if new_entities:
            async_add_entities(new_entities)

    _add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


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


class RoborockCleanAllButton(RoborockDeviceEntity, ButtonEntity):
    """Starts a clean of every currently known room on the device's map."""

    _attr_icon = "mdi:broom"
    _attr_name = "Clean all rooms"

    def __init__(self, coordinator: RoborockRoomsCoordinator, duid: str) -> None:
        super().__init__(coordinator, duid)
        self._attr_unique_id = f"{duid}_clean_all"

    @property
    def available(self) -> bool:
        device = self._device
        return super().available and bool(device and device.rooms)

    async def async_press(self) -> None:
        device = self._device
        if device is None or not device.rooms:
            return
        segments = [room.segment_id for room in device.rooms]
        await _async_clean_rooms(self.hass, self._duid, segments, repeat=1)


class RoborockRoutineButton(RoborockRoutineEntity, ButtonEntity):
    """Triggers a Roborock routine (scene)."""

    _attr_icon = "mdi:play-circle"

    def __init__(self, coordinator: RoborockRoomsCoordinator, duid: str, routine_id: int) -> None:
        super().__init__(coordinator, duid, routine_id)
        self._attr_unique_id = f"{duid}_routine_{routine_id}"

    @property
    def name(self) -> str | None:
        routine = self._routine
        return routine.name if routine else None

    async def async_press(self) -> None:
        await _async_execute_routine(self.hass, self._duid, self._routine_id)
