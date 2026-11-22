logger.debug("Creating GasOwl scale sensors")

entity_id = data.get("entity_id")
entity = hass.states.get(entity_id)

if not entity:
    logger.error(f"Entity not found: {entity_id}")
else:
    installations = entity.attributes.get("installations", [])

    for installation in installations:
        installation_id = installation.get("id")
        installation_name = installation.get("name")
        processed_data = installation.get("processed_data", [])

        for scale in processed_data:
            time = scale.get("time")
            scale_index = scale.get("scale_index")
            side = scale.get("side")
            # The entity ids keep the scale's own number, so existing dashboards still find
            # them; only the names say which side the bottle is on.
            label = "Left" if side == "left" else ("Right" if side == "right" else f"Scale {scale_index}")
            bottle_level = scale.get("bottle_level", 0)  # Default to 0 if not found
            gas_weight = scale.get("gas_weight", 0)  # Default to 0 if not found

            bottle_level_sensor_id = f"gasowl.installation_{installation_id}_scale_{scale_index}_bottle_level"
            bottle_level_sensor_name = (
                f"Installation {installation_id} {label} Bottle Level"
            )

            hass.states.set(
                bottle_level_sensor_id,
                bottle_level,
                {
                    "friendly_name": bottle_level_sensor_name,
                    "unit_of_measurement": "%",
                    "measurement_time": time,
                },
            )

            gas_weight_sensor_id = (
                f"gasowl.installation_{installation_id}_scale_{scale_index}_gas_weight"
            )
            gas_weight_sensor_name = (
                f"Installation {installation_id} {label} Gas Weight"
            )

            hass.states.set(
                gas_weight_sensor_id,
                gas_weight,
                {
                    "friendly_name": gas_weight_sensor_name,
                    "unit_of_measurement": "Kg",
                    "measurement_time": time,
                },
            )
