"""Shared base entity for Roborock Rooms."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RoborockRoomsCoordinator


class RoborockRoomEntity(CoordinatorEntity[RoborockRoomsCoordinator]):
    """Base entity representing a single room/segment on a vacuum's map."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RoborockRoomsCoordinator,
        duid: str,
        segment_id: int,
    ) -> None:
        super().__init__(coordinator)
        self._duid = duid
        self._segment_id = segment_id

    @property
    def _device(self):
        return self.coordinator.data.get(self._duid)

    @property
    def _room(self):
        device = self._device
        if device is None:
            return None
        return next((r for r in device.rooms if r.segment_id == self._segment_id), None)

    @property
    def available(self) -> bool:
        return super().available and self._room is not None

    @property
    def device_info(self) -> DeviceInfo:
        device = self._device
        return DeviceInfo(
            identifiers={(DOMAIN, self._duid)},
            name=device.name if device else self._duid,
            manufacturer="Roborock",
        )
