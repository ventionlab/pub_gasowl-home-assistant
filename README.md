# GasOwl for Home Assistant

Your GasOwl bottle levels in Home Assistant: a device for each installation, a bottle level and a gas
weight sensor for each bottle, and a GasOwl dashboard with one bar for each bottle.

**To set it up, follow the guide "See your gas levels in Home Assistant"** in the GasOwl app, under
Guides (sign in at [app.gasowl.co.nz](https://app.gasowl.co.nz) or in the GasOwl app on your phone).

## Download

Choose **Code › Download ZIP** above, and unzip it. Each folder goes into your Home Assistant
configuration folder, the one that holds `configuration.yaml`:

| In this download | Copy into your configuration folder |
|---|---|
| `custom_components/gasowl_integration/` | `custom_components/` |
| `www/bar-card.js` and `www/gasowl_strategy.js` | `www/` |

Then restart Home Assistant and add GasOwl in **Settings › Devices & services › Add integration**,
with the email and password you use in the GasOwl app. Home Assistant can only read your gas levels.

## Updating

Copy the new `custom_components/gasowl_integration/` and `www/gasowl_strategy.js` over the old ones
and restart Home Assistant. A set-up from version 1.1 or earlier moves to **Devices & services** by
itself; **Settings › Repairs** then asks you to remove the old `configuration.yaml` and `secrets.yaml`
lines. What changed in each version is in [CHANGELOG.md](CHANGELOG.md).

## Your password

Home Assistant keeps your GasOwl sign-in in its own settings. A Home Assistant backup contains it, so do
not share a backup with anyone, us included.

## Help

support@ventionlab.tech · New Zealand 0800 427 695 · Australia +61 2 4012 2479 · USA +1 (940) 289-8972

## Third-party code

`www/bar-card.js` is [bar-card](https://github.com/custom-cards/bar-card) 3.2.0 by Custom cards for
Home Assistant, under the MIT License (`www/bar-card.LICENSE`).

---

GasOwl by [Vention Lab](https://www.ventionlab.tech) · © Vention Lab 2026
