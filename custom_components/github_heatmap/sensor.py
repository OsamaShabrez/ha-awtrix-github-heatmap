from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import (
    AddEntitiesCallback,
)
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from .const import DOMAIN
from .coordinator import (
    GitHubHeatmapCoordinator,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GitHub Heatmap status sensors."""

    coordinator = hass.data[DOMAIN][
        entry.entry_id
    ]

    async_add_entities(
        [
            GitHubHeatmapContributionsSensor(
                coordinator,
                entry,
            ),
            GitHubHeatmapLastUpdateSensor(
                coordinator,
                entry,
            ),
            GitHubHeatmapLastPublishSensor(
                coordinator,
                entry,
            ),
        ]
    )


class GitHubHeatmapContributionsSensor(
    CoordinatorEntity[
        GitHubHeatmapCoordinator
    ],
    SensorEntity,
):
    """GitHub contribution count."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = (
        "contributions"
    )
    _attr_state_class = (
        SensorStateClass.MEASUREMENT
    )
    _attr_icon = "mdi:github"

    def __init__(
        self,
        coordinator: GitHubHeatmapCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            coordinator
        )

        self._attr_unique_id = (
            f"{entry.entry_id}_contributions"
        )

        self._attr_name = "Contributions"

    @property
    def native_value(self) -> int | None:
        """Return last-year contribution count."""

        if not self.coordinator.data:
            return None

        total = self.coordinator.data.get(
            "total",
            {},
        )

        if isinstance(total, dict):
            value = total.get(
                "lastYear"
            )
        else:
            value = total

        try:
            return int(value)
        except (
            TypeError,
            ValueError,
        ):
            return None


class GitHubHeatmapLastUpdateSensor(
    CoordinatorEntity[
        GitHubHeatmapCoordinator
    ],
    SensorEntity,
):
    """Last successful GitHub update."""

    _attr_has_entity_name = True
    _attr_device_class = (
        SensorDeviceClass.TIMESTAMP
    )
    _attr_icon = "mdi:github"

    def __init__(
        self,
        coordinator: GitHubHeatmapCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            coordinator
        )

        self._attr_unique_id = (
            f"{entry.entry_id}_last_update"
        )

        self._attr_name = "Last Update"

    @property
    def native_value(
        self,
    ) -> datetime | None:
        """Return last successful GitHub update."""

        return (
            self.coordinator.last_successful_update
        )


class GitHubHeatmapLastPublishSensor(
    CoordinatorEntity[
        GitHubHeatmapCoordinator
    ],
    SensorEntity,
):
    """Last successful AWTRIX publish."""

    _attr_has_entity_name = True
    _attr_device_class = (
        SensorDeviceClass.TIMESTAMP
    )
    _attr_icon = "mdi:upload-network"

    def __init__(
        self,
        coordinator: GitHubHeatmapCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            coordinator
        )

        self._attr_unique_id = (
            f"{entry.entry_id}_last_publish"
        )

        self._attr_name = "Last Publish"

    @property
    def native_value(
        self,
    ) -> datetime | None:
        """Return last successful AWTRIX publish."""

        return (
            self.coordinator.last_successful_publish
        )
