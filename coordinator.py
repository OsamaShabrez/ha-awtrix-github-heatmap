from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import timedelta
from io import BytesIO

import aiohttp
from PIL import Image, ImageEnhance

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    API_URL,
    APP_NAME,
    GITHUB_USER_API,
    PANEL_H,
    PANEL_W,
)
from .renderer import build_grid, to_row_major

_LOGGER = logging.getLogger(__name__)


class GitHubHeatmapCoordinator(
    DataUpdateCoordinator[dict],
):
    """Fetch GitHub contributions and publish them to AWTRIX."""

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        device_ids: list[str],
        refresh_minutes: int,
        avatar_contrast: float = 1.0,
    ) -> None:
        self.username = username
        self.device_ids = device_ids
        self.refresh_minutes = refresh_minutes
        self.avatar_contrast = avatar_contrast

        self._availability_unsubs = []
        self._last_availability = {}

        super().__init__(
            hass,
            _LOGGER,
            name=f"GitHub Heatmap - {username}",
            update_interval=timedelta(
                minutes=refresh_minutes
            ),
        )

    # ------------------------------------------------------------------
    # MQTT prefix
    # ------------------------------------------------------------------

    def _mqtt_prefix_for_device(
        self,
        device_id: str,
    ) -> str | None:
        """Find the MQTT prefix sensor for a device."""

        registry = er.async_get(self.hass)

        entities = er.async_entries_for_device(
            registry,
            device_id,
            include_disabled_entities=True,
        )

        _LOGGER.debug(
            "Looking for MQTT prefix for device %s; "
            "found %d registered entities",
            device_id,
            len(entities),
        )

        for entity in entities:
            entity_id = entity.entity_id

            if not entity_id.startswith("sensor."):
                continue

            if not entity_id.endswith("_mqtt_prefix"):
                continue

            state = self.hass.states.get(
                entity_id
            )

            if state is None:
                continue

            prefix = state.state.strip()

            if prefix and prefix.lower() not in (
                "unknown",
                "unavailable",
                "none",
            ):
                _LOGGER.debug(
                    "Resolved MQTT prefix '%s' "
                    "for device %s from %s",
                    prefix,
                    device_id,
                    entity_id,
                )

                return prefix

        return None

    def mqtt_prefix(
        self,
        device_id: str,
    ) -> str | None:
        """Return MQTT prefix for a selected device."""

        return self._mqtt_prefix_for_device(
            device_id
        )

    async def async_wait_for_mqtt_prefixes(
        self,
        timeout: int = 30,
    ) -> bool:
        """Wait for all selected AWTRIX MQTT prefix sensors."""

        deadline = (
            self.hass.loop.time()
            + timeout
        )

        while self.hass.loop.time() < deadline:
            missing = []

            for device_id in self.device_ids:
                if not self.mqtt_prefix(
                    device_id
                ):
                    missing.append(
                        device_id
                    )

            if not missing:
                _LOGGER.debug(
                    "All AWTRIX MQTT prefixes "
                    "resolved: %s",
                    self.device_ids,
                )
                return True

            _LOGGER.debug(
                "Waiting for AWTRIX MQTT entities; "
                "missing devices: %s",
                missing,
            )

            await asyncio.sleep(1)

        _LOGGER.error(
            "Timed out waiting for AWTRIX MQTT "
            "prefix sensors; missing devices: %s",
            missing,
        )

        return False

    def app_topic(
        self,
        device_id: str,
    ) -> str | None:
        """Return pushed-app topic."""

        prefix = self.mqtt_prefix(
            device_id
        )

        if not prefix:
            return None

        return (
            f"{prefix}/cmd/apps/pushed/"
            f"{APP_NAME}"
        )

    def availability_topic(
        self,
        device_id: str,
    ) -> str | None:
        """Return availability topic."""

        prefix = self.mqtt_prefix(
            device_id
        )

        if not prefix:
            return None

        return f"{prefix}/availability"

    # ------------------------------------------------------------------
    # GitHub
    # ------------------------------------------------------------------

    async def _async_update_data(
        self,
    ) -> dict:
        """Fetch last year's GitHub contributions."""

        url = API_URL.format(
            username=self.username
        )

        timeout = aiohttp.ClientTimeout(
            total=20
        )

        try:
            async with aiohttp.ClientSession(
                timeout=timeout
            ) as session:
                async with session.get(
                    url,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": (
                            "Home-Assistant-GitHub-Heatmap"
                        ),
                    },
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

            contributions = data.get(
                "contributions",
                [],
            )

            if not contributions:
                raise UpdateFailed(
                    "GitHub API returned no contributions"
                )

            _LOGGER.debug(
                "Fetched %d contribution days; "
                "last-year total=%s",
                len(contributions),
                data.get(
                    "total",
                    {},
                ).get("lastYear"),
            )

            return data

        except UpdateFailed:
            raise

        except Exception as err:
            raise UpdateFailed(
                f"Unable to fetch GitHub contributions: {err}"
            ) from err

    # ------------------------------------------------------------------
    # Avatar
    # ------------------------------------------------------------------

    async def fetch_avatar(
        self,
    ) -> list[int] | None:
        """Fetch GitHub avatar and convert to 8x8 RGB."""

        user_url = GITHUB_USER_API.format(
            username=self.username
        )

        timeout = aiohttp.ClientTimeout(
            total=20
        )

        try:
            async with aiohttp.ClientSession(
                timeout=timeout
            ) as session:

                async with session.get(
                    user_url,
                    headers={
                        "Accept": (
                            "application/vnd.github+json"
                        ),
                        "User-Agent": (
                            "Home-Assistant-GitHub-Heatmap"
                        ),
                    },
                ) as response:
                    response.raise_for_status()
                    user = await response.json()

                avatar_url = user.get(
                    "avatar_url"
                )

                if not avatar_url:
                    return None

                separator = (
                    "&"
                    if "?" in avatar_url
                    else "?"
                )

                avatar_url = (
                    f"{avatar_url}{separator}s=8"
                )

                async with session.get(
                    avatar_url,
                    headers={
                        "User-Agent": (
                            "Home-Assistant-GitHub-Heatmap"
                        ),
                    },
                ) as response:
                    response.raise_for_status()
                    image_data = await response.read()

            image = Image.open(
                BytesIO(image_data)
            ).convert("RGB")

            image = image.resize(
                (8, 8),
                Image.Resampling.BOX,
            )

            if self.avatar_contrast != 1:
                image = ImageEnhance.Contrast(
                    image
                ).enhance(
                    self.avatar_contrast
                )

            pixels = []

            for y in range(8):
                for x in range(8):
                    r, g, b = image.getpixel(
                        (x, y)
                    )

                    pixels.append(
                        (r << 16)
                        | (g << 8)
                        | b
                    )

            return pixels

        except Exception:
            _LOGGER.exception(
                "Failed to fetch GitHub avatar"
            )
            return None

    # ------------------------------------------------------------------
    # Payload
    # ------------------------------------------------------------------

    async def _build_payload(
        self,
    ) -> str:
        """Build AWTRIX bitmap payload."""

        if not self.data:
            raise UpdateFailed(
                "No GitHub data available"
            )

        contributions = self.data.get(
            "contributions",
            [],
        )

        avatar = await self.fetch_avatar()

        pixels = build_grid(
            contributions,
            avatar=avatar,
        )

        bitmap = to_row_major(
            pixels
        )

        raw = bytearray()

        for color in bitmap:
            raw.extend(
                (
                    (color >> 16) & 0xFF,
                    (color >> 8) & 0xFF,
                    color & 0xFF,
                )
            )

        encoded = base64.b64encode(
            raw
        ).decode()

        lifetime_ms = (
            self.refresh_minutes
            * 60
            * 1000
            * 3
        )

        payload = {
            "draw": [
                [
                    "bitmap",
                    0,
                    0,
                    PANEL_W,
                    PANEL_H,
                    encoded,
                ]
            ],
            "lifetimeMs": lifetime_ms,
            "lifetimeExpiry": "remove",
        }

        return json.dumps(
            payload,
            separators=(",", ":"),
        )

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    async def publish(
        self,
    ) -> None:
        """Publish heatmap to all selected devices."""

        if not self.data:
            return

        payload = await self._build_payload()

        successful = 0

        for device_id in self.device_ids:
            topic = self.app_topic(
                device_id
            )

            if not topic:
                _LOGGER.error(
                    "Skipping device %s: "
                    "MQTT prefix unavailable",
                    device_id,
                )
                continue

            try:
                await mqtt.async_publish(
                    self.hass,
                    topic,
                    payload,
                    qos=0,
                    retain=False,
                )

                successful += 1

                _LOGGER.info(
                    "Published GitHub Heatmap "
                    "to %s",
                    topic,
                )

            except Exception:
                _LOGGER.exception(
                    "Failed publishing GitHub "
                    "Heatmap to device %s",
                    device_id,
                )

        if successful == 0:
            raise UpdateFailed(
                "Could not publish GitHub Heatmap "
                "to any selected AWTRIX device"
            )

    # ------------------------------------------------------------------
    # Remove
    # ------------------------------------------------------------------

    async def remove(
        self,
    ) -> None:
        """Remove app from all selected devices."""

        for device_id in self.device_ids:
            topic = self.app_topic(
                device_id
            )

            if not topic:
                _LOGGER.warning(
                    "Cannot remove GitHub Heatmap "
                    "from device %s: "
                    "MQTT prefix unavailable",
                    device_id,
                )
                continue

            try:
                await mqtt.async_publish(
                    self.hass,
                    topic,
                    "",
                    qos=0,
                    retain=False,
                )

                _LOGGER.info(
                    "Removed GitHub Heatmap "
                    "from device %s",
                    device_id,
                )

            except Exception:
                _LOGGER.exception(
                    "Failed removing GitHub Heatmap "
                    "from device %s",
                    device_id,
                )

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    async def subscribe_availability(
        self,
    ) -> None:
        """Subscribe to all selected AWTRIX devices."""

        await self.unsubscribe_availability()

        for device_id in self.device_ids:
            topic = self.availability_topic(
                device_id
            )

            if not topic:
                _LOGGER.warning(
                    "Cannot subscribe to availability "
                    "for device %s",
                    device_id,
                )
                continue

            @callback
            def availability_received(
                msg,
                selected_device_id=device_id,
            ):
                payload = (
                    msg.payload
                    if isinstance(
                        msg.payload,
                        str,
                    )
                    else msg.payload.decode(
                        errors="ignore"
                    )
                )

                previous = (
                    self._last_availability.get(
                        selected_device_id
                    )
                )

                self._last_availability[
                    selected_device_id
                ] = payload

                _LOGGER.debug(
                    "AWTRIX %s availability=%s",
                    selected_device_id,
                    payload,
                )

                if (
                    payload == "online"
                    and previous != "online"
                ):
                    self.hass.async_create_task(
                        self._handle_awtrix_online(
                            selected_device_id
                        )
                    )

            unsub = await mqtt.async_subscribe(
                self.hass,
                topic,
                availability_received,
                qos=0,
            )

            self._availability_unsubs.append(
                unsub
            )

            _LOGGER.debug(
                "Subscribed to %s",
                topic,
            )

    async def unsubscribe_availability(
        self,
    ) -> None:
        """Unsubscribe from availability."""

        for unsub in self._availability_unsubs:
            try:
                unsub()
            except Exception:
                _LOGGER.exception(
                    "Failed to unsubscribe"
                )

        self._availability_unsubs.clear()

    async def _handle_awtrix_online(
        self,
        device_id: str,
    ) -> None:
        """Republish when one AWTRIX comes online."""

        try:
            await asyncio.sleep(2)

            if not self.data:
                await self.async_request_refresh()

            if not self.data:
                return

            payload = await self._build_payload()

            topic = self.app_topic(
                device_id
            )

            if not topic:
                _LOGGER.error(
                    "Cannot republish to device %s: "
                    "MQTT prefix unavailable",
                    device_id,
                )
                return

            await mqtt.async_publish(
                self.hass,
                topic,
                payload,
                qos=0,
                retain=False,
            )

            _LOGGER.info(
                "Republished GitHub Heatmap "
                "to AWTRIX device %s",
                device_id,
            )

        except Exception:
            _LOGGER.exception(
                "Failed to republish GitHub Heatmap "
                "to AWTRIX device %s",
                device_id,
            )

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def async_shutdown(
        self,
    ) -> None:
        """Clean up."""

        await self.unsubscribe_availability()

        await self.remove()
