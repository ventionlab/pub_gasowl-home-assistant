# GasOwl for Home Assistant

Your GasOwl bottle levels in Home Assistant: a level and a gas weight for each scale, and a GasOwl
dashboard with one bar for each bottle.

**To set it up, follow the guide "See your gas levels in Home Assistant"** in the GasOwl app, under
Guides (sign in at [app.gasowl.co.nz](https://app.gasowl.co.nz) or in the GasOwl app on your phone).

## Download

Choose **Code › Download ZIP** above, and unzip it. Each folder goes into your Home Assistant
configuration folder, the one that holds `configuration.yaml`:

| In this download | Copy into your configuration folder |
|---|---|
| `custom_components/gasowl_integration/` | `custom_components/` |
| `python_scripts/create_gasowl_sensors.py` | `python_scripts/` |
| `www/bar-card.js` and `www/gasowl_strategy.js` | `www/` |
| `examples/` | nothing: the lines the guide asks you to add to `configuration.yaml` and `secrets.yaml` |

## Already running it

If your `configuration.yaml` has a different `client_id`, change it to `5ilu9qjm10kr6703ku0hj3nj0q` and restart
Home Assistant. That one signs in for reading only, and keeps working whichever version of the
GasOwl app is on your phone.

## Your password

Keep your GasOwl password in `secrets.yaml` only, never in `configuration.yaml`, and do not share
`secrets.yaml` or a Home Assistant backup, which contains it, with anyone, us included.

## Help

support@ventionlab.tech · New Zealand 0800 427 695 · Australia +61 2 4012 2479 · USA +1 (940) 289-8972

## Third-party code

`www/bar-card.js` is [bar-card](https://github.com/custom-cards/bar-card) 3.2.0 by Custom cards for
Home Assistant, under the MIT License (`www/bar-card.LICENSE`).

---

GasOwl by [Vention Lab](https://www.ventionlab.tech) · © Vention Lab 2026
