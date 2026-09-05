"""The Roborock Rooms integration.

Exposes each room/segment on a Roborock vacuum's map as a sensor (its state
is the segment id used by the cloud API) and a button to clean just that
room, plus a `roborock_rooms.clean_rooms` service to clean an arbitrary set
of rooms in one go.
"""

from __future__ import annotations

import logging
from pathlib import Path

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from roborock.data import UserData
from roborock.devices.device_manager import UserParams, create_device_manager
from roborock.exceptions import RoborockException
from roborock.roborock_typing import RoborockCommand

from .cache import SafeFileCache
from .const import (
    ATTR_DEVICE_ID,
    ATTR_REPEAT,
    ATTR_SEGMENTS,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_USER_DATA,
    DATA_COORDINATORS,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    SERVICE_CLEAN_ROOMS,
)
from .coordinator import RoborockRoomsCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]

CLEAN_ROOMS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_SEGMENTS): vol.All(cv.ensure_list, [vol.Coerce(int)]),
        vol.Optional(ATTR_REPEAT, default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=3)),
    }
)


def _cache_path(hass: HomeAssistant, entry: ConfigEntry) -> Path:
    return Path(hass.config.path(DOMAIN, f"{entry.entry_id}.cache"))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Roborock Rooms from a config entry."""
    email = entry.data[CONF_EMAIL]
    user_data = UserData.from_dict(entry.data[CONF_USER_DATA])
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES)

    coordinator = RoborockRoomsCoordinator(
        hass, email, user_data, _cache_path(hass, entry), scan_interval
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except RoborockException as err:
        raise ConfigEntryNotReady(str(err)) from err

    hass.data.setdefault(DOMAIN, {}).setdefault(DATA_COORDINATORS, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    async def async_clean_rooms(call: ServiceCall) -> None:
        device_entry = dr.async_get(hass).async_get(call.data[ATTR_DEVICE_ID])
        if device_entry is None:
            raise ServiceValidationError("Unknown device")
        duid = next((ident[1] for ident in device_entry.identifiers if ident[0] == DOMAIN), None)
        if duid is None:
            raise ServiceValidationError("Selected device is not a Roborock Rooms vacuum")
        await _async_clean_rooms(hass, duid, call.data[ATTR_SEGMENTS], call.data[ATTR_REPEAT])

    if not hass.services.has_service(DOMAIN, SERVICE_CLEAN_ROOMS):
        hass.services.async_register(
            DOMAIN, SERVICE_CLEAN_ROOMS, async_clean_rooms, schema=CLEAN_ROOMS_SCHEMA
        )

    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinators = hass.data.get(DOMAIN, {}).get(DATA_COORDINATORS, {})
        coordinator = coordinators.pop(entry.entry_id, None)
        if coordinator is not None:
            coordinator.async_shutdown_issues()
        if not coordinators and hass.services.has_service(DOMAIN, SERVICE_CLEAN_ROOMS):
            hass.services.async_remove(DOMAIN, SERVICE_CLEAN_ROOMS)
    return unload_ok


def _find_coordinator_for_duid(hass: HomeAssistant, duid: str) -> RoborockRoomsCoordinator | None:
    for coordinator in hass.data.get(DOMAIN, {}).get(DATA_COORDINATORS, {}).values():
        if duid in coordinator.data:
            return coordinator
    return None


async def _async_clean_rooms(hass: HomeAssistant, duid: str, segments: list[int], repeat: int) -> None:
    """Open a short-lived connection to the account and start a room clean."""
    coordinator = _find_coordinator_for_duid(hass, duid)
    if coordinator is None:
        raise RoborockException(f"Unknown Roborock device duid: {duid}")

    entry_id = next(
        entry_id
        for entry_id, coord in hass.data[DOMAIN][DATA_COORDINATORS].items()
        if coord is coordinator
    )
    entry = hass.config_entries.async_get_entry(entry_id)
    assert entry is not None
    cache = SafeFileCache(_cache_path(hass, entry))
    user_params = UserParams(username=coordinator.email, user_data=coordinator.user_data)

    manager = None
    try:
        manager = await create_device_manager(user_params, cache=cache)
        devices = await manager.get_devices()
        device = next((d for d in devices if d.duid == duid), None)
        if device is None or device.v1_properties is None:
            raise RoborockException(f"Device {duid} not found or does not support room cleaning")
        await device.v1_properties.command.send(
            RoborockCommand.APP_SEGMENT_CLEAN,
            params=[{"segments": segments, "repeat": repeat}],
        )
    finally:
        if manager is not None:
            await manager.close()
        await cache.flush()
