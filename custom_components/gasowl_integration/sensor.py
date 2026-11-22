"""GasOwl sensors: a bottle level and a gas weight for each scale, and a summary sensor.

Each installation is a device, and each of its scales has two sensors, named for the side the
bottle is on. They update on their own, whether or not a dashboard is open, and come back after
a restart. sensor.gasowl is the summary the GasOwl dashboard strategy reads; it keeps the
attributes it had in 1.1, and now also names the real sensors for each scale.
"""

import logging

import voluptuous as vol
from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import (
    CONF_NAME,
    CONF_PASSWORD,
    CONF_USERNAME,
    PERCENTAGE,
    Platform,
    UnitOfMass,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_CLIENT_ID,
    CONF_URL,
    DOMAIN,
    ISSUE_DEPRECATED_YAML,
    ISSUE_DEPRECATED_YAML_IMPORT_FAILED,
    WEB_APP_URL,
)

logger = logging.getLogger(__name__)

# configuration.yaml, as version 1.1 and earlier were set up. Read only to move it across.
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_URL): cv.string,
        vol.Required(CONF_CLIENT_ID): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_NAME, default="GraphQL Sensor"): cv.string,
    }
)

SIDE_LABEL = {"left": "Left", "right": "Right"}


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """A configuration.yaml entry: move it into Settings > Devices & services."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={key: config[key] for key in (CONF_URL, CONF_CLIENT_ID, CONF_USERNAME, CONF_PASSWORD)},
    )
    if result["type"] == FlowResultType.ABORT and result["reason"] != "already_configured":
        logger.error(
            "Could not move the GasOwl entry from configuration.yaml (%s). Add GasOwl in "
            "Settings > Devices & services instead.",
            result["reason"],
        )
        ir.async_create_issue(
            hass,
            DOMAIN,
            ISSUE_DEPRECATED_YAML_IMPORT_FAILED,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_DEPRECATED_YAML_IMPORT_FAILED,
            translation_placeholders={"reason": result["reason"]},
        )
        return
    ir.async_delete_issue(hass, DOMAIN, ISSUE_DEPRECATED_YAML_IMPORT_FAILED)
    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_DEPRECATED_YAML,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_DEPRECATED_YAML,
    )


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities([GasOwlSummarySensor(coordinator, entry)])

    known = set()

    def add_new_scales():
        new = []
        for installation_id, installation in (coordinator.data or {}).items():
            for scale_index in installation["scales"]:
                if (installation_id, scale_index) in known:
                    continue
                known.add((installation_id, scale_index))
                new += [
                    BottleLevelSensor(coordinator, installation_id, scale_index),
                    GasWeightSensor(coordinator, installation_id, scale_index),
                ]
        if new:
            async_add_entities(new)

    add_new_scales()
    entry.async_on_unload(coordinator.async_add_listener(add_new_scales))


class ScaleSensor(CoordinatorEntity, SensorEntity):
    """One reading of one scale on one installation."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    key = None
    label = None

    def __init__(self, coordinator, installation_id, scale_index):
        super().__init__(coordinator)
        self._installation_id = installation_id
        self._scale_index = scale_index
        self._attr_unique_id = f"{installation_id}_scale_{scale_index}_{self.key}"
        installation = coordinator.data[installation_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"installation_{installation_id}")},
            name=installation["name"],
            manufacturer="Vention Lab",
            model="GasOwl",
            serial_number=installation["tube_serial_number"],
            configuration_url=WEB_APP_URL,
        )

    @property
    def _scale(self):
        installation = (self.coordinator.data or {}).get(self._installation_id) or {}
        return installation.get("scales", {}).get(self._scale_index)

    @property
    def available(self):
        return super().available and self._scale is not None

    @property
    def name(self):
        scale = self._scale or {}
        where = SIDE_LABEL.get(scale.get("side"), f"Scale {self._scale_index}")
        return f"{where} {self.label}"

    @property
    def native_value(self):
        scale = self._scale
        return scale.get(self.key) if scale else None

    @property
    def extra_state_attributes(self):
        scale = self._scale or {}
        return {
            "side": scale.get("side"),
            "scale_index": self._scale_index,
            "scale_serial_number": scale.get("serial_number"),
            "measured_at": scale.get("time"),
        }


class BottleLevelSensor(ScaleSensor):
    key = "bottle_level"
    label = "bottle level"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:gas-cylinder"
    _attr_suggested_display_precision = 0


class GasWeightSensor(ScaleSensor):
    key = "gas_weight"
    label = "gas weight"
    _attr_device_class = SensorDeviceClass.WEIGHT
    _attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS
    _attr_suggested_display_precision = 1


class GasOwlSummarySensor(CoordinatorEntity, SensorEntity):
    """sensor.gasowl: when GasOwl last answered, and every installation's latest readings."""

    _attr_name = "GasOwl"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:owl"
    # The attributes change with every reading; keep them out of the recorder's history.
    _unrecorded_attributes = frozenset({"installations"})

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_summary"

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        @callback
        def scale_sensor_registered(event):
            # Name a scale sensor here as soon as it has an entity id, rather than at the
            # next poll, so the dashboard never falls back to the old python script.
            if event.data.get("action") != "create":
                return
            registered = er.async_get(self.hass).async_get(event.data["entity_id"])
            if registered and registered.platform == DOMAIN and registered.unique_id != self.unique_id:
                self.async_write_ha_state()

        self.async_on_remove(
            self.hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, scale_sensor_registered)
        )

    @property
    def native_value(self):
        return self.coordinator.last_success

    @property
    def extra_state_attributes(self):
        registry = er.async_get(self.hass)

        def entity_id(installation_id, scale_index, key):
            return registry.async_get_entity_id(
                Platform.SENSOR, DOMAIN, f"{installation_id}_scale_{scale_index}_{key}"
            )

        installations = []
        for installation_id, installation in (self.coordinator.data or {}).items():
            readings = []
            for scale_index, scale in installation["scales"].items():
                if scale["time"] is None:
                    continue
                readings.append(
                    {
                        "scale_index": scale_index,
                        "side": scale["side"],
                        "time": scale["time"],
                        "bottle_level": scale["bottle_level"],
                        "gas_weight": scale["gas_weight"],
                        "bottle_level_entity": entity_id(installation_id, scale_index, "bottle_level"),
                        "gas_weight_entity": entity_id(installation_id, scale_index, "gas_weight"),
                    }
                )
            installations.append(
                {
                    "id": installation_id,
                    "name": installation["name"],
                    "left_scale_index": installation["left_scale_index"],
                    "processed_data": readings,
                }
            )
        return {"installations": installations}
