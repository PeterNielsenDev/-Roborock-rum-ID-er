"""Per-room cleaning settings.

Deliberately free of Home Assistant imports so the grouping logic can be
unit-tested on its own.

Roborock vacuums only apply ONE suction/water/mop setting at a time - the
segment-clean command itself just takes a list of rooms and a repeat count.
To give each room its own settings, rooms with identical settings are grouped
and the groups are cleaned one after another (see `group_segments`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

DEFAULT_OPTION = "default"

MIN_REPEAT = 1
MAX_REPEAT = 3


@dataclass(frozen=True)
class RoomCleanSettings:
    """Cleaning settings for one room. `None` means "leave the vacuum's own setting"."""

    fan_power: int | None = None
    water_box_mode: int | None = None
    mop_mode: int | None = None
    repeat: int = MIN_REPEAT

    @property
    def motor_overrides(self) -> dict[str, int]:
        """The suction/water/mop values that must be set before cleaning this room."""
        overrides = {
            "fan_power": self.fan_power,
            "water_box_mode": self.water_box_mode,
            "mop_mode": self.mop_mode,
        }
        return {key: value for key, value in overrides.items() if value is not None}


class RoomSettingsStore:
    """In-memory settings for every room, keyed by (vacuum duid, segment id)."""

    def __init__(self) -> None:
        self._settings: dict[tuple[str, int], RoomCleanSettings] = {}

    def get(self, duid: str, segment_id: int) -> RoomCleanSettings:
        return self._settings.get((duid, segment_id), RoomCleanSettings())

    def update(self, duid: str, segment_id: int, **changes: int | None) -> None:
        self._settings[(duid, segment_id)] = replace(self.get(duid, segment_id), **changes)


def group_segments(
    segments: list[int], settings_for: Callable[[int], RoomCleanSettings]
) -> list[tuple[RoomCleanSettings, list[int]]]:
    """Group rooms that share identical settings, keeping first-seen order."""
    groups: dict[RoomCleanSettings, list[int]] = {}
    for segment_id in segments:
        groups.setdefault(settings_for(segment_id), []).append(segment_id)
    return list(groups.items())


def build_motor_params(
    settings: RoomCleanSettings, current: dict[str, int | None]
) -> dict[str, int]:
    """Params for `set_clean_motor_mode`: overrides on top of the vacuum's current values."""
    params = {key: value for key, value in current.items() if value is not None}
    params.update(settings.motor_overrides)
    return params
