"""Config flow for Roborock Rooms.

Two ways to sign in, mirroring the official Roborock app:
- Email + password.
- Email only, followed by a one-time code sent by email.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from roborock.exceptions import RoborockException
from roborock.web_api import RoborockApiClient

from .const import CONF_USER_DATA, DOMAIN

_LOGGER = logging.getLogger(__name__)

CONF_CODE = "code"

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Optional(CONF_PASSWORD, default=""): str,
    }
)
STEP_CODE_SCHEMA = vol.Schema({vol.Required(CONF_CODE): str})


class RoborockRoomsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Roborock Rooms."""

    VERSION = 1

    def __init__(self) -> None:
        self._email: str | None = None
        self._client: RoborockApiClient | None = None

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
