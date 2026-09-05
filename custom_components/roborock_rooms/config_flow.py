"""Config flow for Roborock Rooms.

Two ways to sign in, mirroring the official Roborock app:
- Email + password.
- Email only, followed by a one-time code sent by email.

Also provides a reauth flow (triggered automatically if the stored login
token is rejected) and an options flow to change the polling interval.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from roborock.exceptions import RoborockException
from roborock.web_api import RoborockApiClient

from .const import (
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_USER_DATA,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

CONF_CODE = "code"

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Optional(CONF_PASSWORD, default=""): str,
    }
)
STEP_CODE_SCHEMA = vol.Schema({vol.Required(CONF_CODE): str})
STEP_REAUTH_SCHEMA = vol.Schema({vol.Optional(CONF_PASSWORD, default=""): str})


class RoborockRoomsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Roborock Rooms."""

    VERSION = 1

    def __init__(self) -> None:
        self._email: str | None = None
        self._client: RoborockApiClient | None = None
        self._reauth_entry: ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> RoborockRoomsOptionsFlow:
        return RoborockRoomsOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            password = user_input[CONF_PASSWORD].strip()
            await self.async_set_unique_id(email.lower())
            self._abort_if_unique_id_configured()

            client = RoborockApiClient(email)
            try:
                if password:
                    user_data = await client.pass_login(password)
                else:
                    await client.request_code()
                    self._email = email
                    self._client = client
                    return await self.async_step_code()
            except RoborockException as err:
                _LOGGER.debug("Login failed for %s: %s", email, err)
                errors["base"] = "invalid_auth"
            else:
                return self.async_create_entry(
                    title=email,
                    data={CONF_EMAIL: email, CONF_USER_DATA: user_data.as_dict()},
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None and self._client is not None and self._email is not None:
            try:
                user_data = await self._client.code_login(user_input[CONF_CODE].strip())
            except RoborockException as err:
                _LOGGER.debug("Code login failed for %s: %s", self._email, err)
                errors["base"] = "invalid_auth"
            else:
                return self.async_create_entry(
                    title=self._email,
                    data={CONF_EMAIL: self._email, CONF_USER_DATA: user_data.as_dict()},
                )

        return self.async_show_form(
            step_id="code",
            data_schema=STEP_CODE_SCHEMA,
            errors=errors,
            description_placeholders={"email": self._email or ""},
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication when the stored login token is rejected."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        self._email = entry_data[CONF_EMAIL]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None and self._email is not None:
            password = user_input[CONF_PASSWORD].strip()
            client = RoborockApiClient(self._email)
            try:
                if password:
                    user_data = await client.pass_login(password)
                else:
                    await client.request_code()
                    self._client = client
                    return await self.async_step_reauth_code()
            except RoborockException as err:
                _LOGGER.debug("Reauth login failed for %s: %s", self._email, err)
                errors["base"] = "invalid_auth"
            else:
                return self._update_reauth_entry(user_data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_SCHEMA,
            errors=errors,
            description_placeholders={"email": self._email or ""},
        )

    async def async_step_reauth_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None and self._client is not None and self._email is not None:
            try:
                user_data = await self._client.code_login(user_input[CONF_CODE].strip())
            except RoborockException as err:
                _LOGGER.debug("Reauth code login failed for %s: %s", self._email, err)
                errors["base"] = "invalid_auth"
            else:
                return self._update_reauth_entry(user_data)

        return self.async_show_form(
            step_id="reauth_code",
            data_schema=STEP_CODE_SCHEMA,
            errors=errors,
            description_placeholders={"email": self._email or ""},
        )

    def _update_reauth_entry(self, user_data) -> ConfigFlowResult:
        assert self._reauth_entry is not None
        self.hass.config_entries.async_update_entry(
            self._reauth_entry,
            data={CONF_EMAIL: self._email, CONF_USER_DATA: user_data.as_dict()},
        )
        self.hass.async_create_task(
            self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
        )
        return self.async_abort(reason="reauth_successful")


class RoborockRoomsOptionsFlow(OptionsFlow):
    """Options flow to change the polling interval.

    Stores the entry on a private attribute rather than the inherited
    `config_entry` - newer Home Assistant versions expose that as a
    read-only property, so assigning to it in `__init__` (the old,
    long-standard pattern) raises AttributeError there.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self._entry.options.get(
            CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES
        )
        schema = vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL_MINUTES, default=current): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL_MINUTES, max=MAX_SCAN_INTERVAL_MINUTES),
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
