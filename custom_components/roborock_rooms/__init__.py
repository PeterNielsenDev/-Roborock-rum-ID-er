"""The Roborock Rooms integration.

Exposes each room/segment on a Roborock vacuum's map as a sensor (its state
is the segment id used by the cloud API) and a button to clean just that
room, plus a `roborock_rooms.clean_rooms` service to clean an arbitrary set
of rooms in one go. Each room can also have its own suction / water flow /
mop route / repeat settings (select and number entities). Also exposes each
account-defined routine (scene) as a button, plus a `roborock_rooms.run_routine`
service to trigger one by id.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from roborock.data import RoborockStateCode, UserData
from roborock.devices.device_manager import UserParams, create_device_manager
from roborock.exceptions import RoborockException
from roborock.roborock_typing import RoborockCommand

from .cache import SafeFileCache
from .const import (
    ATTR_DEVICE_ID,
    ATTR_REPEAT,
    ATTR_ROUTINE_ID,
    ATTR_SEGMENTS,
    ATTR_USE_ROOM_SETTINGS,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_USER_DATA,
    DATA_ACTIVE_QUEUES,
    DATA_COORDINATORS,
    DATA_ROOM_SETTINGS,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    QUEUE_GROUP_TIMEOUT_SECONDS,
    QUEUE_POLL_SECONDS,
    QUEUE_START_GRACE_SECONDS,
    SERVICE_CLEAN_ROOMS,
    SERVICE_RUN_ROUTINE,
)
from .coordinator import RoborockRoomsCoordinator
from .settings import (
    MAX_REPEAT,
    MIN_REPEAT,
    RoomCleanSettings,
    RoomSettingsStore,
    build_motor_params,
    group_segments,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON, Platform.SELECT, Platform.NUMBER]

CLEAN_ROOMS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_SEGMENTS): vol.All(cv.ensure_list, [vol.Coerce(int)]),
        # Omitted -> each room's own "repeat" setting is used.
        vol.Optional(ATTR_REPEAT): vol.All(vol.Coerce(int), vol.Range(min=MIN_REPEAT, max=MAX_REPEAT)),
        vol.Optional(ATTR_USE_ROOM_SETTINGS, default=True): cv.boolean,
    }
)

RUN_ROUTINE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_ROUTINE_ID): vol.Coerce(int),
    }
)

# The vacuum is done with a group once it is back on the dock / idle.
_FINISHED_STATES = {RoborockStateCode.idle, RoborockStateCode.charging, RoborockStateCode.charging_complete}
# Give up on the remaining groups if the vacuum hits one of these.
_FAILED_STATES = {RoborockStateCode.error, RoborockStateCode.device_offline}


def _cache_path(hass: HomeAssistant, entry: ConfigEntry) -> Path:
    return Path(hass.config.path(DOMAIN, f"{entry.entry_id}.cache"))


def _room_settings(hass: HomeAssistant) -> RoomSettingsStore:
    return hass.data.setdefault(DOMAIN, {}).setdefault(DATA_ROOM_SETTINGS, RoomSettingsStore())


def _duid_from_device_id(hass: HomeAssistant, device_id: str) -> str:
    device_entry = dr.async_get(hass).async_get(device_id)
    if device_entry is None:
        raise ServiceValidationError("Unknown device")
    duid = next((ident[1] for ident in device_entry.identifiers if ident[0] == DOMAIN), None)
    if duid is None:
        raise ServiceValidationError("Selected device is not a Roborock Rooms vacuum")
    return duid


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
    _room_settings(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    async def async_clean_rooms(call: ServiceCall) -> None:
        duid = _duid_from_device_id(hass, call.data[ATTR_DEVICE_ID])
        await _async_clean_rooms(
            hass,
            duid,
            call.data[ATTR_SEGMENTS],
            repeat=call.data.get(ATTR_REPEAT),
            use_room_settings=call.data[ATTR_USE_ROOM_SETTINGS],
        )

    if not hass.services.has_service(DOMAIN, SERVICE_CLEAN_ROOMS):
        hass.services.async_register(
            DOMAIN, SERVICE_CLEAN_ROOMS, async_clean_rooms, schema=CLEAN_ROOMS_SCHEMA
        )

    async def async_run_routine(call: ServiceCall) -> None:
        duid = _duid_from_device_id(hass, call.data[ATTR_DEVICE_ID])
        await _async_execute_routine(hass, duid, call.data[ATTR_ROUTINE_ID])

    if not hass.services.has_service(DOMAIN, SERVICE_RUN_ROUTINE):
        hass.services.async_register(
            DOMAIN, SERVICE_RUN_ROUTINE, async_run_routine, schema=RUN_ROUTINE_SCHEMA
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
        if not coordinators:
            if hass.services.has_service(DOMAIN, SERVICE_CLEAN_ROOMS):
                hass.services.async_remove(DOMAIN, SERVICE_CLEAN_ROOMS)
            if hass.services.has_service(DOMAIN, SERVICE_RUN_ROUTINE):
                hass.services.async_remove(DOMAIN, SERVICE_RUN_ROUTINE)
    return unload_ok


def _find_coordinator_for_duid(hass: HomeAssistant, duid: str) -> RoborockRoomsCoordinator | None:
    for coordinator in hass.data.get(DOMAIN, {}).get(DATA_COORDINATORS, {}).values():
        if duid in coordinator.data:
            return coordinator
    return None


@asynccontextmanager
async def _device_session(hass: HomeAssistant, duid: str, purpose: str) -> AsyncIterator:
    """Open a short-lived connection to the account and yield one vacuum device."""
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
    cache = SafeFileCache(hass, _cache_path(hass, entry))
    user_params = UserParams(username=coordinator.email, user_data=coordinator.user_data)

    manager = None
    try:
        manager = await create_device_manager(user_params, cache=cache)
        devices = await manager.get_devices()
        device = next((d for d in devices if d.duid == duid), None)
        if device is None or device.v1_properties is None:
            raise RoborockException(f"Device {duid} not found or does not support {purpose}")
        yield device
    finally:
        if manager is not None:
            await manager.close()
        await cache.flush()


async def _async_clean_rooms(
    hass: HomeAssistant,
    duid: str,
    segments: list[int],
    repeat: int | None = None,
    use_room_settings: bool = True,
) -> None:
    """Clean the given rooms, applying each room's own settings.

    The vacuum can only use one suction/water/mop setting at a time, so rooms
    with identical settings are cleaned together and different groups run one
    after another. A single group is started right away; several groups are
    queued in the background (the vacuum must finish one before the next).
    """
    store = _room_settings(hass)

    def settings_for(segment_id: int) -> RoomCleanSettings:
        settings = store.get(duid, segment_id) if use_room_settings else RoomCleanSettings()
        return replace(settings, repeat=repeat) if repeat is not None else settings

    groups = group_segments(segments, settings_for)
    if not groups:
        return

    if len(groups) == 1:
        async with _device_session(hass, duid, "room cleaning") as device:
            await _async_start_group(device, *groups[0])
        return

    active_queues: set[str] = hass.data[DOMAIN].setdefault(DATA_ACTIVE_QUEUES, set())
    if duid in active_queues:
        raise HomeAssistantError(
            "Rooms with different settings are already being cleaned one after another on this vacuum"
        )
    active_queues.add(duid)
    hass.async_create_background_task(
        _async_run_group_queue(hass, duid, groups, active_queues),
        name=f"{DOMAIN} clean queue {duid}",
    )


async def _async_run_group_queue(
    hass: HomeAssistant,
    duid: str,
    groups: list[tuple[RoomCleanSettings, list[int]]],
    active_queues: set[str],
) -> None:
    try:
        async with _device_session(hass, duid, "room cleaning") as device:
            for index, group in enumerate(groups):
                await _async_start_group(device, *group)
                if index < len(groups) - 1:
                    await _async_wait_until_finished(device)
    except (RoborockException, TimeoutError) as err:
        _LOGGER.warning("Stopped the room cleaning queue for %s: %s", duid, err)
    finally:
        active_queues.discard(duid)


async def _async_start_group(device, settings: RoomCleanSettings, segments: list[int]) -> None:
    """Apply a group's suction/water/mop settings, then start cleaning its rooms."""
    props = device.v1_properties
    if settings.motor_overrides:
        await props.status.refresh()
        status = props.status
        params = build_motor_params(
            settings,
            {
                "fan_power": status.fan_power,
                "water_box_mode": status.water_box_mode,
                "mop_mode": status.mop_mode,
            },
        )
        try:
            await props.command.send(RoborockCommand.SET_CLEAN_MOTOR_MODE, params=[params])
        except RoborockException:
            # Older models do not know the combined command; set each value on its own.
            _LOGGER.debug("set_clean_motor_mode failed, falling back to individual commands", exc_info=True)
            individual = {
                "fan_power": RoborockCommand.SET_CUSTOM_MODE,
                "water_box_mode": RoborockCommand.SET_WATER_BOX_CUSTOM_MODE,
                "mop_mode": RoborockCommand.SET_MOP_MODE,
            }
            for key, value in settings.motor_overrides.items():
                await props.command.send(individual[key], params=[value])
    await props.command.send(
        RoborockCommand.APP_SEGMENT_CLEAN,
        params=[{"segments": segments, "repeat": settings.repeat}],
    )


async def _async_wait_until_finished(device) -> None:
    """Block until the vacuum has started, finished cleaning and is idle/docked again."""
    loop = asyncio.get_running_loop()
    started_at = loop.time()
    seen_active = False
    while loop.time() - started_at < QUEUE_GROUP_TIMEOUT_SECONDS:
        await asyncio.sleep(QUEUE_POLL_SECONDS)
        status = device.v1_properties.status
        await status.refresh()
        if status.state in _FAILED_STATES:
            raise RoborockException(f"vacuum reported state {status.state.name}")
        if status.state in _FINISHED_STATES:
            if seen_active:
                return
            if loop.time() - started_at > QUEUE_START_GRACE_SECONDS:
                raise RoborockException("vacuum never started cleaning")
        else:
            seen_active = True
    raise TimeoutError("timed out waiting for the vacuum to finish")


async def _async_execute_routine(hass: HomeAssistant, duid: str, routine_id: int) -> None:
    """Open a short-lived connection to the account and trigger a routine."""
    async with _device_session(hass, duid, "routines") as device:
        await device.v1_properties.routines.execute_routine(routine_id)
