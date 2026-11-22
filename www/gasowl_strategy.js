// File: www/gasowl_strategy.js

class GasOwlStrategy {
    static async generate(config, hass) {
        // Ensure the sensor entity is found
        const sensorEntityId = "sensor.gasowl";
        const sensorState = hass.states[sensorEntityId];

        if (!sensorState) {
            console.error(`Sensor entity not found: ${sensorEntityId}`);
            return {
                views: [
                    {
                        title: "Error",
                        path: "error",
                        cards: [
                            {
                                type: "markdown",
                                content: `Error: Sensor entity not found: ${sensorEntityId}`
                            }
                        ]
                    }
                ]
            };
        }

        // Extract installation data from the sensor state attributes
        const installationData = sensorState.attributes.installations || [];

        // Version 1.2 and later name a real sensor for each scale. Only an older setup, which
        // has none, needs the python script to make its stand-in sensors.
        const hasRealSensors = installationData.every(installation =>
            installation.processed_data.every(scale => scale.bottle_level_entity)
        );
        if (!hasRealSensors) {
            try {
                await hass.callService('python_script', 'create_gasowl_sensors', { entity_id: sensorEntityId });
            } catch (err) {
                console.warn("GasOwl: python_script.create_gasowl_sensors is not available", err);
            }
        }

        const views = installationData.map(installation => {
            const installationId = installation.id;
            const installationName = installation.name;
            // Left bottle first, then right, so the bars sit the way the bottles do.
            // A scale whose side is unknown keeps its own number and goes last.
            const sideOrder = { left: 0, right: 1 };
            const scales = [...installation.processed_data].sort(
                (a, b) => (sideOrder[a.side] ?? 2) - (sideOrder[b.side] ?? 2)
            );
            const scaleLabel = scale =>
                scale.side === "left" ? "Left" : scale.side === "right" ? "Right" : `Scale ${scale.scale_index}`;

            const barCardEntities = scales.map(scale => ({
                entity: scale.bottle_level_entity
                    || `gasowl.installation_${installationId}_scale_${scale.scale_index}_bottle_level`,
                name: `${scaleLabel(scale)}\nUpdated: ${new Date(scale.time).toLocaleString()}`,
                // name: `Scale ${scale.scale_index}`,
                severity: [
                    { from: 0, to: 25, color: 'red' },
                    { from: 25, to: 50, color: 'orange' },
                    { from: 50, to: 75, color: 'yellow' },
                    { from: 75, to: 100, color: 'green' }
                ],
                height: "200px"
            }));

            return {
                title: `${installationName}`,
                path: `installation-${installationId}`,
                cards: [
                    {
                        type: "markdown",
                        content: `### GasOwl: ${installationName}`
                    },
                    {
                        type: "custom:bar-card",
                        entities: barCardEntities,
                        columns: 2,
                        direction: "up",
                    }
                ]
            };
        });

        return { views };
    }
}

customElements.define("ll-strategy-gasowl_strategy", GasOwlStrategy);
