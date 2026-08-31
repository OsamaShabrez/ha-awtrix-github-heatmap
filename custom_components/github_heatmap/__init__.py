from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_DEVICE_ID,
    CONF_ENABLED,
    CONF_ICON_ID,
    CONF_REFRESH,
    CONF_USERNAME,
    DEFAULT_ENABLED,
    DEFAULT_ICON_ID,
    DEFAULT_REFRESH,
    DOMAIN,
    SERVICE_REFRESH,
)
from .coordinator import GitHubHeatmapCoordinator

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor"]


async def async_setup(
    hass: HomeAssistant,
    config: dict,
) -> bool:
    """Set up GitHub Heatmap."""

    hass.data.setdefault(DOMAIN, {})

    async def handle_refresh(call: ServiceCall) -> None:
        """Manually refresh all enabled GitHub Heatmap entries."""

        coordinators = list(
            hass.data.get(DOMAIN, {}).values()
        )

        if not coordinators:
            _LOGGER.debug(
                "Manual refresh requested but no "
                "GitHub Heatmap entries are loaded"
            )
            return

        for coordinator in coordinators:
            if not coordinator.enabled:
                continue

            await coordinator.async_refresh_and_publish()

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
    """Set up a GitHub Heatmap config entry."""

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

    device_ids = list(
        dict.fromkeys(device_ids)
    )

    refresh = int(
        entry.options.get(
            CONF_REFRESH,
            DEFAULT_REFRESH,
        )
    )

    enabled = bool(
        entry.options.get(
            CONF_ENABLED,
            DEFAULT_ENABLED,
        )
    )

    icon_id = str(
        entry.options.get(
            CONF_ICON_ID,
            DEFAULT_ICON_ID,
        )
        or ""
    ).strip()

    coordinator = GitHubHeatmapCoordinator(
        hass=hass,
        username=username,
        device_ids=device_ids,
        refresh_minutes=refresh,
        enabled=enabled,
        icon_id=icon_id,
        entry_id=entry.entry_id,
    )

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(
        entry,
        PLATFORMS,
    )

    if not enabled:
        _LOGGER.info(
            "GitHub Heatmap disabled; removing app "
            "from %d selected AWTRIX device(s)",
            len(device_ids),
        )

        await coordinator.remove()
        return True

    try:
        await coordinator.async_config_entry_first_refresh()

        await coordinator.async_wait_for_mqtt_prefixes()

        await coordinator.subscribe_availability()

        await coordinator.publish()

        coordinator.start_auto_publish()

    except Exception:
        _LOGGER.exception(
            "Initial GitHub Heatmap setup failed"
        )

        # Do not unload the integration.
        # Future coordinator refreshes can recover.
        coordinator.start_auto_publish()

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Unload GitHub Heatmap and remove its AWTRIX apps."""

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry,
        PLATFORMS,
    )

    coordinator = hass.data[DOMAIN].pop(
        entry.entry_id,
        None,
    )

    if coordinator is not None:
        await coordinator.async_shutdown()

    return unload_ok
