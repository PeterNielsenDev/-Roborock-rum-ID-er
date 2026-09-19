"""Select platform for Roborock Rooms.

Per room: suction power, water flow and mop route. "default" means the
integration leaves the vacuum's own setting untouched when cleaning that room.
The available choices come from the vacuum model itself.
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import _room_settings
from .const import DATA_COORDINATORS, DOMAIN
from .coordinator import RoborockRoomsCoordinator
from .entity import RoborockRoomEntity
from .settings import DEFAULT_OPTION

# setting key -> (name suffix, RoborockDeviceRooms attribute holding the options, icon)
SETTINGS: dict[str, tuple[str, str, str]] = {
    "fan_power": ("suction", "fan_options", "mdi:fan"),
    "water_box_mode": ("water flow", "water_options", "mdi:water"),
    "mop_mode": ("mop route", "route_options", "mdi:map-marker-path"),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: RoborockRoomsCoordinator = hass.data[DOMAIN][DATA_COORDINATORS][entry.entry_id]
    known: set[tuple[str, int, str]] = set()

    @callback
    def _add_new_entities() -> None:
        new_entities = []
        for duid, device in coordinator.data.items():
            for room in device.rooms:
                for key, (_, options_attr, _) in SETTINGS.items():
                    # Models without e.g. a mop route setting simply get no such select.
                    if not getattr(device, options_attr):
                        continue
                    ident = (duid, room.segment_id, key)
                    if ident not in known:
                        known.add(ident)
                        new_entities.append(
                            RoborockRoomSettingSelect(coordinator, duid, room.segment_id, key)
                        )
        if new_entities:
            async_add_entities(new_entities)

    _add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


class RoborockRoomSettingSelect(RoborockRoomEntity, SelectEntity, RestoreEntity):
    """Chooses one cleaning setting for a single room."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: RoborockRoomsCoordinator, duid: str, segment_id: int, key: str
    ) -> None:
        super().__init__(coordinator, duid, segment_id)
        self._key = key
        self._suffix, self._options_attr, self._attr_icon = SETTINGS[key]
        self._attr_unique_id = f"{duid}_{segment_id}_{key}"

    @property
    def _choices(self) -> dict[str, int]:
        device = self._device
        return getattr(device, self._options_attr) if device else {}

    @property
    def name(self) -> str | None:
        room = self._room
        return f"{room.name} {self._suffix}" if room else None

    @property
    def options(self) -> list[str]:
        return [DEFAULT_OPTION, *self._choices]

    @property
    def current_option(self) -> str:
        code = getattr(_room_settings(self.hass).get(self._duid, self._segment_id), self._key)
        return next((name for name, value in self._choices.items() if value == code), DEFAULT_OPTION)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in self._choices:
            self._apply(self._choices[last_state.state])

    async def async_select_option(self, option: str) -> None:
        self._apply(self._choices.get(option))
        self.async_write_ha_state()

    def _apply(self, code: int | None) -> None:
        _room_settings(self.hass).update(self._duid, self._segment_id, **{self._key: code})
