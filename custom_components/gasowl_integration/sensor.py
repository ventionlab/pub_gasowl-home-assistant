import base64
import json
import logging
import time
from datetime import datetime, timedelta

import boto3
import requests
import voluptuous as vol
from botocore.exceptions import BotoCoreError, ClientError
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_NAME
from homeassistant.helpers.entity import Entity
import homeassistant.helpers.config_validation as cv

logger = logging.getLogger(__name__)

CONF_URL = "url"
CONF_CLIENT_ID = "client_id"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
SCAN_INTERVAL = timedelta(minutes=5)

COGNITO_REGION = "ap-southeast-2"
# Renew the ID token this long before it expires, so a poll never goes out on a stale one.
TOKEN_RENEW_MARGIN = 300  # seconds
REQUEST_TIMEOUT = 30  # seconds

# GasOwl returns only the signed-in owner's own installations. "export" is the read-only
# role, used whenever the token offers it; otherwise "user" is named explicitly.
EXPORT_ROLE = "export"
USER_ROLE = "user"
HASURA_CLAIMS = "https://hasura.io/jwt/claims"

_QUERY = """
query getData {
    installation%s {
        id
        name
        tube {
            dev_eui
            serial_number
            left_scale_index
            scales(order_by: {index: asc}) {
                id
                index
                serial_number
                processed_data(limit: 1, order_by: {time: desc}) {
                    bottle_level
                    gas_weight
                    id
                    time
                }
            }
        }
    }
}
"""
QUERY = {
    EXPORT_ROLE: _QUERY % "",
    USER_ROLE: _QUERY % "(where: {account_id: {_is_null: false}})",
}

# GasOwl's minimum-version check starts its refusal with this.
APP_UPDATE_REQUIRED = "APP_UPDATE_REQUIRED"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_URL): cv.string,
        vol.Required(CONF_CLIENT_ID): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_NAME, default="GraphQL Sensor"): cv.string,
    }
)


def setup_platform(hass, config, add_entities, discovery_info=None):
    session = CognitoSession(
        config[CONF_CLIENT_ID], config[CONF_USERNAME], config[CONF_PASSWORD]
    )
    add_entities(
        [GraphQLSensor(config[CONF_URL], session, config[CONF_NAME])],
        True,
    )


class SignInError(Exception):
    """GasOwl would not sign this login in."""


class CognitoSession:
    """Signs in with the password once, then keeps the ID token fresh with the refresh token.

    The password is used again only when the refresh token stops being accepted (it
    expires, or the account was signed out everywhere).
    """

    def __init__(self, client_id, username, password):
        self._client_id = client_id
        self._username = username
        self._password = password
        self._client = boto3.client(service_name="cognito-idp", region_name=COGNITO_REGION)
        self._id_token = None
        self._refresh_token = None
        self._expires_at = 0.0

    def id_token(self, force_renew=False):
        """A current ID token, renewing or signing in only when needed."""
        if (
            self._id_token
            and not force_renew
            and time.time() < self._expires_at - TOKEN_RENEW_MARGIN
        ):
            return self._id_token

        if self._refresh_token:
            try:
                self._authenticate(
                    "REFRESH_TOKEN_AUTH", {"REFRESH_TOKEN": self._refresh_token}
                )
                logger.debug("Renewed the GasOwl token")
                return self._id_token
            except ClientError as err:
                # Only an expired or revoked refresh token sends us back to the password.
                # Anything else (throttling, an AWS fault) fails this poll and keeps the
                # refresh token for the next one.
                if err.response.get("Error", {}).get("Code") != "NotAuthorizedException":
                    raise
                logger.info("GasOwl no longer accepts the saved sign-in, signing in again")
                self._refresh_token = None

        self._sign_in_with_password()
        return self._id_token

    def _sign_in_with_password(self):
        try:
            self._authenticate(
                "USER_PASSWORD_AUTH",
                {"USERNAME": self._username, "PASSWORD": self._password},
            )
        except ClientError as err:
            error = err.response.get("Error", {})
            message = error.get("Message", "")
            if APP_UPDATE_REQUIRED in message:
                raise SignInError(
                    "GasOwl refused the sign-in because the GasOwl app on your phone is "
                    "older than the minimum version. Update the GasOwl app, open it and "
                    "sign in once, and this integration will sign in at its next update. "
                    f"({message.split(APP_UPDATE_REQUIRED, 1)[1].lstrip(': ').rstrip('.')})"
                ) from None
            raise SignInError(
                f"GasOwl refused the sign-in ({error.get('Code', 'error')}): {message}"
            ) from None
        logger.info("Signed in to GasOwl")

    def _authenticate(self, flow, parameters):
        response = self._client.initiate_auth(
            ClientId=self._client_id, AuthFlow=flow, AuthParameters=parameters
        )
        result = response.get("AuthenticationResult")
        if not result:
            raise SignInError(
                f"GasOwl asked for an extra sign-in step ({response.get('ChallengeName')}). "
                "Sign in to the GasOwl app with this login first."
            )
        self._id_token = result["IdToken"]
        self._expires_at = time.time() + result.get("ExpiresIn", 3600)
        # A refresh normally returns no new refresh token; keep the one we have.
        if result.get("RefreshToken"):
            self._refresh_token = result["RefreshToken"]


def _allowed_roles(id_token):
    """The Hasura roles this ID token offers. Read only to choose a role, never trusted."""
    try:
        payload = id_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload)).get(HASURA_CLAIMS) or {}
        if isinstance(claims, str):
            claims = json.loads(claims)
        claims = {key.lower(): value for key, value in claims.items()}
        return list(claims.get("x-hasura-allowed-roles") or [])
    except (IndexError, ValueError, AttributeError, TypeError):
        return []


def _side(scale_index, left_scale_index):
    """"left" or "right" for a scale, as GasOwl itself decides it, or None if unknown.

    Which of a Hub's two scales is on the left is set per Hub (left_scale_index), and the
    GasOwl app can swap it, so it is never assumed from the scale's own number.
    """
    if left_scale_index is None:
        return None
    return "left" if scale_index == left_scale_index else "right"


def _token_rejected(errors):
    return any(
        (e.get("extensions") or {}).get("code") == "invalid-jwt"
        or "JWTExpired" in (e.get("message") or "")
        for e in errors
    )


class GraphQLSensor(Entity):
    def __init__(self, url, session, name):
        self._url = url
        self._session = session
        self._name = name
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    def update(self):
        logger.debug("Starting update for %s", self._name)
        try:
            data = self._query()
            if data.get("errors") and _token_rejected(data["errors"]):
                logger.debug("GasOwl rejected the token, renewing it and asking again")
                data = self._query(force_renew=True)
        except SignInError as err:
            logger.error("%s", err)
            self._state = "Error"
            return
        except (requests.exceptions.RequestException, BotoCoreError, ClientError, ValueError) as err:
            logger.error("Error fetching GasOwl data: %s", err)
            self._state = "Error"
            return

        if data.get("errors"):
            # Keep the last good data rather than blanking the dashboard for a cycle.
            logger.warning(
                "GasOwl returned an error, keeping the last data: %s",
                "; ".join(e.get("message", "") for e in data["errors"]),
            )
            self._state = "Error"
            return

        logger.debug("Response data: %s", data)
        installations = (data.get("data") or {}).get("installation") or []
        installation_list = []

        for installation in installations:
            tube = installation.get("tube")
            if tube:
                scales = tube.get("scales", [])
                left_scale_index = tube.get("left_scale_index")
                processed_data_list = []

                for scale in scales:
                    processed_data = scale.get("processed_data", [])
                    if processed_data:
                        for data_point in processed_data:
                            processed_data_list.append(
                                {
                                    "scale_index": scale["index"],
                                    "side": _side(scale["index"], left_scale_index),
                                    "time": data_point.get("time"),
                                    "bottle_level": data_point.get("bottle_level"),
                                    "gas_weight": data_point.get("gas_weight"),
                                }
                            )

                installation_list.append(
                    {
                        "id": installation["id"],
                        "name": installation["name"],
                        "left_scale_index": left_scale_index,
                        "processed_data": processed_data_list,
                    }
                )

        self._attributes = {"installations": installation_list}
        self._state = datetime.now().isoformat()
        logger.debug("Stored installation data in attributes: %s", self._attributes)

    def _query(self, force_renew=False):
        token = self._session.id_token(force_renew)
        role = EXPORT_ROLE if EXPORT_ROLE in _allowed_roles(token) else USER_ROLE
        logger.debug("Reading GasOwl as the %s role", role)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Hasura-Role": role,
        }
        response = requests.post(
            self._url,
            json={"query": QUERY[role]},
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
