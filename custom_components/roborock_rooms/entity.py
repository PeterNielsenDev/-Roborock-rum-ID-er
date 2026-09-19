"""Shared base entities for Roborock Rooms."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VACUUM_MODEL
from .coordinator import RoborockRoomsCoordinator


def async_ensure_vacuum_devices(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: RoborockRoomsCoordinator
) -> None:
    """Register the vacuum devices, so room devices can point at them via `via_device`."""
    registry = dr.async_get(hass)
    for duid, device in coordinator.data.items():
        registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, duid)},
            name=device.name,
            manufacturer="Roborock",
            model=VACUUM_MODEL,
        )


class RoborockDeviceEntity(CoordinatorEntity[RoborockRoomsCoordinator]):
    """Base entity representing a single Roborock vacuum on the account."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RoborockRoomsCoordinator, duid: str) -> None:
        super().__init__(coordinator)
        self._duid = duid

    @property
    def _device(self):
        return self.coordinator.data.get(self._duid)

    @property
    def available(self) -> bool:
        return super().available and self._device is not None

    @property
    def device_info(self) -> DeviceInfo:
        device = self._device
        return DeviceInfo(
            identifiers={(DOMAIN, self._duid)},
            name=device.name if device else self._duid,
            manufacturer="Roborock",
            model=VACUUM_MODEL,
        )


class RoborockRoomEntity(RoborockDeviceEntity):
    """Base entity representing a single room/segment on a vacuum's map."""

    def __init__(
        self,
        coordinator: RoborockRoomsCoordinator,
        duid: str,
        segment_id: int,
    ) -> None:
        super().__init__(coordinator, duid)
        self._segment_id = segment_id

    @property
    def _room(self):
        device = self._device
        if device is None:
            return None
        return next((r for r in device.rooms if r.segment_id == self._segment_id), None)

    @property
    def available(self) -> bool:
        return super().available and self._room is not None


class RoborockRoomSettingEntity(RoborockRoomEntity):
    """A per-room cleaning setting, shown on its own "room" device under the vacuum.

    Grouping a room's settings on a device of their own keeps the vacuum's page
    short: it just lists its rooms, and each room shows only its own settings.
    """

    @property
    def device_info(self) -> DeviceInfo:
        room = self._room
        device = self._device
        vacuum_name = device.name if device else self._duid
        room_name = room.name if room else f"Room {self._segment_id}"
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._duid}_{self._segment_id}")},
            name=f"{vacuum_name} {room_name}",
            manufacturer="Roborock",
            model="Room",
            via_device=(DOMAIN, self._duid),
        )


class RoborockRoutineEntity(RoborockDeviceEntity):
    """Base entity representing a single routine (scene) for a vacuum."""

    def __init__(
        self,
        coordinator: RoborockRoomsCoordinator,
        duid: str,
        routine_id: int,
    ) -> None:
        super().__init__(coordinator, duid)
        self._routine_id = routine_id

    @property
    def _routine(self):
        device = self._device
        if device is None:
            return None
        return next((r for r in device.routines if r.routine_id == self._routine_id), None)

    @property
    def available(self) -> bool:
        return super().available and self._routine is not None
