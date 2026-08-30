from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_DEVICE_ID,
    CONF_ENABLED,
    CONF_REFRESH,
    CONF_USERNAME,
    DEFAULT_ENABLED,
    DEFAULT_REFRESH,
    DOMAIN,
)
from .coordinator import GitHubHeatmapCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = []


async def async_setup(
    hass: HomeAssistant,
    config: dict,
) -> bool:
    """Set up GitHub Heatmap."""

    hass.data.setdefault(DOMAIN, {})

    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Set up GitHub Heatmap."""

    username = entry.options.get(
        CONF_USERNAME,
        entry.data[CONF_USERNAME],
    )

    device_ids = entry.options.get(
        CONF_DEVICE_ID,
        entry.data[CONF_DEVICE_ID],
    )

    if isinstance(device_ids, str):
        device_ids = [device_ids]

    device_ids = sorted(set(device_ids))

    refresh = entry.options.get(
        CONF_REFRESH,
        DEFAULT_REFRESH,
    )

    enabled = entry.options.get(
        CONF_ENABLED,
        DEFAULT_ENABLED,
    )

    _LOGGER.debug(
        "Setting up GitHub Heatmap: "
        "username=%s devices=%s refresh=%s enabled=%s",
        username,
        device_ids,
        refresh,
        enabled,
    )

    coordinator = GitHubHeatmapCoordinator(
        hass=hass,
        username=username,
        device_ids=device_ids,
        refresh_minutes=refresh,
        avatar_contrast=1.0,
    )

    hass.data[DOMAIN][entry.entry_id] = coordinator

    if not enabled:
        _LOGGER.info(
            "GitHub Heatmap disabled"
        )

        await coordinator.remove()
        return True

    try:
        await coordinator.async_config_entry_first_refresh()

        await coordinator.async_wait_for_mqtt_prefixes()

        await coordinator.publish()

        await coordinator.subscribe_availability()

    except Exception:
        _LOGGER.exception(
            "Initial GitHub Heatmap setup failed"
        )

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Unload GitHub Heatmap."""

    coordinator = hass.data[DOMAIN].pop(
        entry.entry_id,
        None,
    )

    if coordinator:
        await coordinator.async_shutdown()

    return True
