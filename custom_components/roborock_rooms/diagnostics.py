"""Diagnostics support for Roborock Rooms."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DATA_COORDINATORS, DOMAIN
from .coordinator import RoborockRoomsCoordinator

TO_REDACT = {"user_data", "email"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: RoborockRoomsCoordinator = hass.data[DOMAIN][DATA_COORDINATORS][entry.entry_id]
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "devices": {
            duid: {
                "name": device.name,
                "error": device.error,
                "rooms": [
                    {
                        "segment_id": room.segment_id,
                        "name": room.name,
                        "map_flag": room.map_flag,
                        "map_name": room.map_name,
                    }
                    for room in device.rooms
                ],
            }
            for duid, device in coordinator.data.items()
        },
    }
