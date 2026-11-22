"""Polls GasOwl for the owner's installations, on its own, every few minutes."""

import logging

import requests
from botocore.exceptions import BotoCoreError, ClientError
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AppUpdateRequired, AuthError, CognitoSession, GasOwlClient, GasOwlError
from .const import (
    CONF_CLIENT_ID,
    CONF_REFRESH_TOKEN,
    CONF_URL,
    DEFAULT_CLIENT_ID,
    DEFAULT_URL,
    DOMAIN,
    ISSUE_APP_UPDATE_REQUIRED,
    SCAN_INTERVAL,
    STALE_DATA_GRACE,
)

logger = logging.getLogger(__name__)


class GasOwlCoordinator(DataUpdateCoordinator):
    """One per GasOwl account. Its data is api.parse()'s installations dict."""

    def __init__(self, hass, entry):
        super().__init__(
            hass,
            logger,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self._client = None
        self.last_success = None

    def _fetch(self):
        if self._client is None:
            data = self.config_entry.data
            session = CognitoSession(
                data.get(CONF_CLIENT_ID, DEFAULT_CLIENT_ID),
                data[CONF_USERNAME],
                data[CONF_PASSWORD],
                refresh_token=data.get(CONF_REFRESH_TOKEN),
            )
            self._client = GasOwlClient(data.get(CONF_URL, DEFAULT_URL), session)
        return self._client.fetch()

    async def _async_update_data(self):
        try:
            installations = await self.hass.async_add_executor_job(self._fetch)
        except AuthError as err:
            # Home Assistant asks the owner to sign in again.
            raise ConfigEntryAuthFailed(str(err)) from err
        except (GasOwlError, requests.exceptions.RequestException, BotoCoreError, ClientError, ValueError) as err:
            if isinstance(err, AppUpdateRequired):
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    f"{ISSUE_APP_UPDATE_REQUIRED}_{self.config_entry.entry_id}",
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key=ISSUE_APP_UPDATE_REQUIRED,
                    translation_placeholders={"username": self.config_entry.title},
                )
            if (
                self.data is not None
                and self.last_success is not None
                and dt_util.utcnow() - self.last_success < STALE_DATA_GRACE
            ):
                logger.warning("%s; keeping the last GasOwl data", err)
                return self.data
            raise UpdateFailed(str(err)) from err

        ir.async_delete_issue(
            self.hass, DOMAIN, f"{ISSUE_APP_UPDATE_REQUIRED}_{self.config_entry.entry_id}"
        )
        self.last_success = dt_util.utcnow()
        self._save_refresh_token()
        return installations

    def _save_refresh_token(self):
        """Keep the newest refresh token in the config entry, so a restart can use it."""
        token = self._client.session.refresh_token
        if token and token != self.config_entry.data.get(CONF_REFRESH_TOKEN):
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={**self.config_entry.data, CONF_REFRESH_TOKEN: token},
            )
