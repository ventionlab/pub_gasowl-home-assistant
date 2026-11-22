"""Set up GasOwl from Settings > Devices & services: sign in with the GasOwl app's login."""

import logging

import requests
import voluptuous as vol
from botocore.exceptions import BotoCoreError, ClientError
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import AppUpdateRequired, AuthError, CognitoSession, GasOwlClient, GasOwlError
from .const import (
    CONF_CLIENT_ID,
    CONF_REFRESH_TOKEN,
    CONF_URL,
    DEFAULT_CLIENT_ID,
    DEFAULT_URL,
    DOMAIN,
    EARLIER_CLIENT_IDS,
)

logger = logging.getLogger(__name__)

SECTION_ADVANCED = "advanced"
EMAIL = TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username"))
PASSWORD = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
)


def _entry_data(username, password, url=None, client_id=None):
    """What a config entry keeps. The API address and sign-in client are kept only where the
    owner changed them, so a later version's defaults (for example a sign-in client made for
    integrations) reach every owner who simply updates the integration."""
    data = {CONF_USERNAME: str(username).strip(), CONF_PASSWORD: str(password)}
    if url and url != DEFAULT_URL:
        data[CONF_URL] = url
    if client_id and client_id != DEFAULT_CLIENT_ID and client_id not in EARLIER_CLIENT_IDS:
        data[CONF_CLIENT_ID] = client_id
    return data


def _check_login(data):
    """Sign in and read once. Returns the refresh token to keep. Runs in the executor."""
    session = CognitoSession(
        data.get(CONF_CLIENT_ID, DEFAULT_CLIENT_ID), data[CONF_USERNAME], data[CONF_PASSWORD]
    )
    GasOwlClient(data.get(CONF_URL, DEFAULT_URL), session).fetch()
    return session.refresh_token


class GasOwlConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _validate(self, data):
        """({}, refresh token) when the login works, else ({"base": reason}, None)."""
        try:
            token = await self.hass.async_add_executor_job(_check_login, data)
        except AuthError:
            return {"base": "invalid_auth"}, None
        except AppUpdateRequired:
            return {"base": "app_update_required"}, None
        except (GasOwlError, requests.exceptions.RequestException, BotoCoreError, ClientError, ValueError) as err:
            logger.warning("Could not reach GasOwl: %s", err)
            return {"base": "cannot_connect"}, None
        except Exception:  # noqa: BLE001 - shown to the owner as "unknown", logged in full
            logger.exception("Unexpected error checking the GasOwl login")
            return {"base": "unknown"}, None
        return {}, token

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            advanced = user_input.get(SECTION_ADVANCED) or {}
            data = _entry_data(
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                advanced.get(CONF_URL),
                advanced.get(CONF_CLIENT_ID),
            )
            await self.async_set_unique_id(data[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()
            errors, token = await self._validate(data)
            if not errors:
                return self.async_create_entry(
                    title=data[CONF_USERNAME], data={**data, CONF_REFRESH_TOKEN: token}
                )

        # The API address and sign-in client stay folded away: owners never need them, and
        # they let the same integration be pointed at GasOwl's test environment.
        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): EMAIL,
                vol.Required(CONF_PASSWORD): PASSWORD,
                vol.Required(SECTION_ADVANCED): section(
                    vol.Schema(
                        {
                            vol.Optional(CONF_URL, default=DEFAULT_URL): str,
                            vol.Optional(CONF_CLIENT_ID, default=DEFAULT_CLIENT_ID): str,
                        }
                    ),
                    {"collapsed": True},
                ),
            }
        )
        if user_input is not None:
            # Keep what was typed, apart from the password, when the form comes back.
            schema = self.add_suggested_values_to_schema(
                schema, {k: v for k, v in user_input.items() if k != CONF_PASSWORD}
            )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            data = {**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            data.pop(CONF_REFRESH_TOKEN, None)
            errors, token = await self._validate(data)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data={**data, CONF_REFRESH_TOKEN: token}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD}),
            description_placeholders={"username": entry.data[CONF_USERNAME]},
            errors=errors,
        )

    async def async_step_import(self, import_data):
        """Move a configuration.yaml entry from version 1.1 or earlier into a config entry."""
        data = _entry_data(
            import_data[CONF_USERNAME],
            import_data[CONF_PASSWORD],
            import_data.get(CONF_URL),
            import_data.get(CONF_CLIENT_ID),
        )
        await self.async_set_unique_id(data[CONF_USERNAME].lower())
        self._abort_if_unique_id_configured()
        errors, token = await self._validate(data)
        if errors:
            return self.async_abort(reason=errors["base"])
        return self.async_create_entry(
            title=data[CONF_USERNAME], data={**data, CONF_REFRESH_TOKEN: token}
        )
