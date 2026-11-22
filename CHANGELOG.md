# Changelog

## 1.2.0

- Set up in **Settings > Devices & services**, with the email and password you use for the GasOwl app. Nothing goes in `configuration.yaml` or `secrets.yaml` any more.
- Signs in through GasOwl's client for integrations: it can read your gas levels and change nothing, and it keeps working whatever version of the GasOwl app is on your phone.
- Each installation is a device, with a bottle level (%) and a gas weight (kg) sensor for each scale, named for the side the bottle is on. They update every 5 minutes on their own, whether or not a dashboard is open, and come back after a restart, so they work in automations, history and statistics. The python script is no longer needed.
- Stays signed in across restarts. If your password changes, Home Assistant asks you to sign in again. If the GasOwl app on your phone needs updating, a notice says so in **Settings > Repairs**.
- A short outage at GasOwl keeps the last readings showing, for up to an hour.
- A `configuration.yaml` entry from 1.1 or earlier is moved across on its own, and **Settings > Repairs** then asks you to remove it.
- An installation's device can be deleted once GasOwl no longer lists it.
- `sensor.gasowl` and the GasOwl dashboard keep working as before.

## 1.1.0

- Signs in once and then stays signed in, instead of signing in with your password every hour.
- Reads only: it uses GasOwl's read-only access wherever your login offers it.
- Capitals in your email no longer stop it finding your installations.
- The dashboard's bars say Left and Right, the way the bottles sit.
- Quieter logs: nothing at info level during normal polling, and the installation's address is no longer fetched.
- `boto3` is listed in the integration's requirements, and the login is kept in `secrets.yaml`.

## 1.0.0

- First version.
