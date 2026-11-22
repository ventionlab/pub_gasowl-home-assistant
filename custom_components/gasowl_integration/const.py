from datetime import timedelta

DOMAIN = "gasowl_integration"

CONF_URL = "url"
CONF_CLIENT_ID = "client_id"
CONF_REFRESH_TOKEN = "refresh_token"

# GasOwl's production API, and GasOwl's sign-in client for integrations: it can read an
# owner's gas levels and change nothing, and it keeps working whatever version of the GasOwl
# app is on the owner's phone. A config entry keeps these only where the owner changed them
# (config_flow._entry_data), so changing a default here moves every owner at their next
# update. A refresh token from the old client is then refused once, and the integration
# signs in with the password.
DEFAULT_URL = "https://api.gasowl.co.nz/api/v1/graphql"
DEFAULT_CLIENT_ID = "5ilu9qjm10kr6703ku0hj3nj0q"
# The GasOwl app's own client, which 1.1 and earlier signed in through. An entry from
# configuration.yaml that names it moves to the default instead.
EARLIER_CLIENT_IDS = ("3frmc6bcso8av3lhtquq3f8ddh",)
WEB_APP_URL = "https://app.gasowl.co.nz"

SCAN_INTERVAL = timedelta(minutes=5)
# A poll that fails keeps the last data, and the sensors stay available, for this long.
# GasOwl readings arrive every two hours or so, so a short outage loses nothing.
STALE_DATA_GRACE = timedelta(hours=1)

ISSUE_APP_UPDATE_REQUIRED = "app_update_required"
ISSUE_DEPRECATED_YAML = "deprecated_yaml"
ISSUE_DEPRECATED_YAML_IMPORT_FAILED = "deprecated_yaml_import_failed"
