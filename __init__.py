from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    CONF_DEVICE_ID,
    CONF_ENABLED,
    CONF_REFRESH,
    CONF_USERNAME,
    DEFAULT_ENABLED,
    DEFAULT_REFRESH,
    DOMAIN,
    SERVICE_REFRESH,
)
from .coordinator import GitHubHeatmapCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor"]


async def async_setup(
    hass: HomeAssistant,
    config: dict,
) -> bool:
    """Set up GitHub Heatmap."""

    hass.data.setdefault(DOMAIN, {})

    async def handle_refresh(call: ServiceCall) -> None:
        """Refresh all enabled GitHub Heatmap entries."""

        coordinators = list(
            hass.data.get(DOMAIN, {}).values()
        )

        for coordinator in coordinators:
            if coordinator.enabled:
                await coordinator.async_refresh_and_publish()

    if not hass.services.has_service(
        DOMAIN,
        SERVICE_REFRESH,
    ):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REFRESH,
            handle_refresh,
            schema=vol.Schema({}),
        )

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

    refresh = int(
        entry.options.get(
            CONF_REFRESH,
            DEFAULT_REFRESH,
        )
    )

    enabled = entry.options.get(
        CONF_ENABLED,
        DEFAULT_ENABLED,
    )

    coordinator = GitHubHeatmapCoordinator(
        hass=hass,
        username=username,
        device_ids=device_ids,
        refresh_minutes=refresh,
        avatar_contrast=1.0,
        enabled=enabled,
        entry_id=entry.entry_id,
    )

    hass.data[DOMAIN][entry.entry_id] = coordinator

    if not enabled:
        await coordinator.remove()
        return True

    try:
        await coordinator.async_config_entry_first_refresh()

        await coordinator.async_wait_for_mqtt_prefixes()

        await coordinator.publish()

        await coordinator.subscribe_availability()

        coordinator.start_auto_publish()

        await hass.config_entries.async_forward_entry_setups(
            entry,
            PLATFORMS,
        )

    except Exception:
        _LOGGER.exception(
            "Initial GitHub Heatmap setup failed"
        )

        # Keep the coordinator alive so a later scheduled
        # refresh can recover automatically.
        coordinator.start_auto_publish()

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Unload GitHub Heatmap."""

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry,
        PLATFORMS,
    )

    coordinator = hass.data[DOMAIN].pop(
        entry.entry_id,
        None,
    )

    if coordinator:
        await coordinator.async_shutdown()

    return unload_ok
