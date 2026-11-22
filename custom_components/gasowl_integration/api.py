"""GasOwl's API: signing in through Cognito and reading an owner's installations.

Nothing here imports Home Assistant, and everything here blocks, so Home Assistant calls it
from its executor.
"""

import base64
import json
import logging
import time

import boto3
import requests
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

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

# GasOwl starts a refusal that asks for the GasOwl app to be updated with this.
APP_UPDATE_REQUIRED = "APP_UPDATE_REQUIRED"
# Cognito's answers that mean the email or password is wrong, or the account is gone.
AUTH_ERROR_CODES = {"NotAuthorizedException", "UserNotFoundException"}


class GasOwlError(Exception):
    """GasOwl answered, but not with the data."""


class SignInError(GasOwlError):
    """GasOwl would not sign this login in."""


class AuthError(SignInError):
    """The email or password is wrong, or the account no longer exists."""


class AppUpdateRequired(SignInError):
    """GasOwl refused the sign-in until the GasOwl app on the owner's phone is updated."""


class CognitoSession:
    """Signs in with the password once, then keeps the ID token fresh with the refresh token.

    The password is used again only when the refresh token stops being accepted (it
    expires, or the account was signed out everywhere). A refresh token kept from an
    earlier run is used first, so a restart needs no password sign-in either.
    """

    def __init__(self, client_id, username, password, refresh_token=None):
        self._client_id = client_id
        self._username = username
        self._password = password
        self._refresh_token = refresh_token
        self._client = None
        self._id_token = None
        self._expires_at = 0.0

    @property
    def refresh_token(self):
        return self._refresh_token

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
            code, message = error.get("Code", "error"), error.get("Message", "")
            if APP_UPDATE_REQUIRED in message:
                raise AppUpdateRequired(
                    "GasOwl refused the sign-in because the GasOwl app on your phone is "
                    "older than the minimum version. Update the GasOwl app, open it and "
                    "sign in once, and this integration will sign in at its next update. "
                    f"({message.split(APP_UPDATE_REQUIRED, 1)[1].lstrip(': ').rstrip('.')})"
                ) from None
            if code in AUTH_ERROR_CODES:
                raise AuthError(f"GasOwl refused the sign-in ({code}): {message}") from None
            raise SignInError(f"GasOwl refused the sign-in ({code}): {message}") from None
        logger.info("Signed in to GasOwl")

    def _authenticate(self, flow, parameters):
        if self._client is None:
            self._client = boto3.client(service_name="cognito-idp", region_name=COGNITO_REGION)
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


def allowed_roles(id_token):
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


def side(scale_index, left_scale_index):
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


def parse(reply):
    """The owner's installations from a GraphQL reply, keyed by installation id.

    Each carries its Hub's serial number, its left_scale_index and its scales keyed by index,
    each scale with its side and its latest reading (None where it has none yet).
    """
    installations = {}
    for installation in (reply.get("data") or {}).get("installation") or []:
        tube = installation.get("tube")
        if not tube:
            continue
        left_scale_index = tube.get("left_scale_index")
        scales = {}
        for scale in tube.get("scales") or []:
            points = scale.get("processed_data") or []
            point = points[0] if points else {}
            scales[scale["index"]] = {
                "index": scale["index"],
                "side": side(scale["index"], left_scale_index),
                "serial_number": scale.get("serial_number"),
                "bottle_level": point.get("bottle_level"),
                "gas_weight": point.get("gas_weight"),
                "time": point.get("time"),
            }
        installations[installation["id"]] = {
            "id": installation["id"],
            "name": installation["name"],
            "tube_serial_number": tube.get("serial_number"),
            "left_scale_index": left_scale_index,
            "scales": scales,
        }
    return installations


class GasOwlClient:
    """Reads the signed-in owner's installations."""

    def __init__(self, url, session):
        self._url = url
        self.session = session

    def fetch(self):
        """The owner's installations (see parse). Raises GasOwlError or a transport error."""
        reply = self._query()
        if reply.get("errors") and _token_rejected(reply["errors"]):
            logger.debug("GasOwl rejected the token, renewing it and asking again")
            reply = self._query(force_renew=True)
        if reply.get("errors"):
            raise GasOwlError(
                "GasOwl returned an error: "
                + "; ".join(e.get("message", "") for e in reply["errors"])
            )
        logger.debug("Response data: %s", reply)
        return parse(reply)

    def _query(self, force_renew=False):
        token = self.session.id_token(force_renew)
        role = EXPORT_ROLE if EXPORT_ROLE in allowed_roles(token) else USER_ROLE
        logger.debug("Reading GasOwl as the %s role", role)
        response = requests.post(
            self._url,
            json={"query": QUERY[role]},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Hasura-Role": role,
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
