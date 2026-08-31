from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from io import BytesIO

import aiohttp
from PIL import Image

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    API_RETRIES,
    API_URL,
    APP_NAME,
    AVATAR_CACHE_HOURS,
    GITHUB_USER_API,
    MQTT_RETRIES,
    MQTT_RETRY_DELAY,
    PANEL_H,
    PANEL_W,
)
from .renderer import build_grid, to_row_major

_LOGGER = logging.getLogger(__name__)


class GitHubHeatmapCoordinator(
    DataUpdateCoordinator[dict],
):
    """Coordinate GitHub data and AWTRIX publishing."""

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        device_ids: list[str],
        refresh_minutes: int,
        enabled: bool,
        icon_id: str,
        entry_id: str,
    ) -> None:
        self.username = username
        self.device_ids = list(device_ids)
        self.refresh_minutes = refresh_minutes
        self.enabled = enabled
        self.icon_id = icon_id.strip()
        self.entry_id = entry_id

        self.last_successful_update: (
            datetime | None
        ) = None

        self.last_successful_publish: (
            datetime | None
        ) = None

        self._avatar_pixels: (
            list[int] | None
        ) = None

        self._avatar_url: str | None = None
        self._avatar_fetched_at: float | None = None

        self._availability_unsubs: list = []
        self._last_availability: dict[
            str, str
        ] = {}

        self._publish_lock = asyncio.Lock()
        self._auto_publish = False
        self._update_listener_unsub = None

        super().__init__(
            hass,
            _LOGGER,
            name=f"GitHub Heatmap - {username}",
            update_interval=timedelta(
                minutes=refresh_minutes
            ),
        )

    # ------------------------------------------------------------------
    # MQTT discovery
    # ------------------------------------------------------------------

    def mqtt_prefix(
        self,
        device_id: str,
    ) -> str | None:
        """Find the AWTRIX MQTT prefix from its HA device."""

        registry = er.async_get(self.hass)

        entities = er.async_entries_for_device(
            registry,
            device_id,
            include_disabled_entities=True,
        )

        for entity in entities:
            state = self.hass.states.get(
                entity.entity_id
            )

            if state is None:
                continue

            entity_id = entity.entity_id.lower()
            state_name = (
                state.name or ""
            ).lower()

            # Prefer the exact entity-id pattern.
            is_prefix_sensor = (
                entity_id.endswith("_mqtt_prefix")
                or "mqtt prefix" in state_name
            )

            if not is_prefix_sensor:
                continue

            value = state.state.strip()

            if value and value.lower() not in {
                "unknown",
                "unavailable",
                "none",
            }:
                return value

        _LOGGER.debug(
            "MQTT prefix unavailable for AWTRIX "
            "device %s",
            device_id,
        )

        return None

    def app_topic(
        self,
        device_id: str,
    ) -> str | None:
        """Build the AWTRIX pushed-app topic."""

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
        """Build the AWTRIX availability topic."""

        prefix = self.mqtt_prefix(
            device_id
        )

        if not prefix:
            return None

        return f"{prefix}/availability"

    async def async_wait_for_mqtt_prefixes(
        self,
        timeout: int = 30,
    ) -> bool:
        """Wait for MQTT prefix sensors to become available."""

        deadline = (
            self.hass.loop.time()
            + timeout
        )

        while self.hass.loop.time() < deadline:
            missing = [
                device_id
                for device_id in self.device_ids
                if not self.mqtt_prefix(device_id)
            ]

            if not missing:
                return True

            await asyncio.sleep(1)

        _LOGGER.warning(
            "Timed out waiting for MQTT prefix sensors "
            "for AWTRIX devices: %s",
            missing,
        )

        return False

    # ------------------------------------------------------------------
    # GitHub
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict:
        """Fetch the last 365 days of GitHub contributions."""

        url = API_URL.format(
            username=self.username
        )

        timeout = aiohttp.ClientTimeout(
            total=20
        )

        last_error: Exception | None = None

        for attempt in range(
            1,
            API_RETRIES + 1,
        ):
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

                self.last_successful_update = (
                    datetime.now(timezone.utc)
                )

                _LOGGER.debug(
                    "GitHub update successful: "
                    "%d days, total=%s",
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
                last_error = err

                if attempt < API_RETRIES:
                    delay = 2 ** (
                        attempt - 1
                    )

                    _LOGGER.debug(
                        "GitHub request failed "
                        "(%d/%d), retrying in %ss",
                        attempt,
                        API_RETRIES,
                        delay,
                    )

                    await asyncio.sleep(delay)

        raise UpdateFailed(
            f"GitHub request failed after "
            f"{API_RETRIES} attempts: {last_error}"
        ) from last_error

    # ------------------------------------------------------------------
    # Avatar
    # ------------------------------------------------------------------

    async def fetch_avatar(
        self,
        force: bool = False,
    ) -> list[int] | None:
        """Fetch and cache the GitHub avatar."""

        now = time.monotonic()

        if (
            not force
            and self._avatar_pixels is not None
            and self._avatar_fetched_at is not None
            and (
                now - self._avatar_fetched_at
                < AVATAR_CACHE_HOURS * 3600
            )
        ):
            return self._avatar_pixels

        timeout = aiohttp.ClientTimeout(
            total=20
        )

        try:
            async with aiohttp.ClientSession(
                timeout=timeout
            ) as session:
                async with session.get(
                    GITHUB_USER_API.format(
                        username=self.username
                    ),
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
                    return self._avatar_pixels

                # Do not re-download an unchanged avatar
                # during the cache period.
                if (
                    self._avatar_pixels is not None
                    and avatar_url == self._avatar_url
                    and not force
                ):
                    self._avatar_fetched_at = now
                    return self._avatar_pixels

                separator = (
                    "&"
                    if "?" in avatar_url
                    else "?"
                )

                sized_url = (
                    f"{avatar_url}{separator}s=8"
                )

                async with session.get(
                    sized_url,
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

            pixels: list[int] = []

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

            if len(pixels) != 64:
                raise ValueError(
                    "Avatar conversion produced "
                    f"{len(pixels)} pixels"
                )

            self._avatar_pixels = pixels
            self._avatar_url = avatar_url
            self._avatar_fetched_at = now

            _LOGGER.debug(
                "GitHub avatar cache refreshed"
            )

            return pixels

        except Exception as err:
            _LOGGER.warning(
                "GitHub avatar refresh failed; "
                "keeping cached avatar: %s",
                err,
            )

            return self._avatar_pixels

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    async def _build_payload(
        self,
    ) -> str | None:
        """Render the current contribution data."""

        if not self.data:
            return None

        contributions = self.data.get(
            "contributions",
            [],
        )

        if not contributions:
            return None

        avatar = None

        if not self.icon_id:
            avatar = await self.fetch_avatar()

        pixels = build_grid(
            contributions,
            avatar=avatar,
            reserve_left=bool(self.icon_id),
        )

        bitmap = to_row_major(
            pixels
        )

        expected_pixels = (
            PANEL_W * PANEL_H
        )

        if len(bitmap) != expected_pixels:
            raise ValueError(
                f"Renderer returned "
                f"{len(bitmap)} pixels; "
                f"expected {expected_pixels}"
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

        if self.icon_id:
            payload["icon"] = self.icon_id

        return json.dumps(
            payload,
            separators=(",", ":"),
        )

    # ------------------------------------------------------------------
    # MQTT publishing
    # ------------------------------------------------------------------

    async def _publish_to_device(
        self,
        device_id: str,
        payload: str,
    ) -> bool:
        """Publish the app to one device with retries."""

        topic = self.app_topic(
            device_id
        )

        if not topic:
            _LOGGER.debug(
                "Skipping AWTRIX device %s: "
                "MQTT prefix unavailable",
                device_id,
            )
            return False

        for attempt in range(
            1,
            MQTT_RETRIES + 1,
        ):
            try:
                await mqtt.async_publish(
                    self.hass,
                    topic,
                    payload,
                    qos=0,
                    retain=False,
                )

                return True

            except Exception as err:
                if attempt < MQTT_RETRIES:
                    delay = (
                        MQTT_RETRY_DELAY
                        * 2 ** (
                            attempt - 1
                        )
                    )

                    _LOGGER.debug(
                        "MQTT publish failed for "
                        "device %s (%d/%d); "
                        "retrying in %ss",
                        device_id,
                        attempt,
                        MQTT_RETRIES,
                        delay,
                    )

                    await asyncio.sleep(delay)

                else:
                    _LOGGER.warning(
                        "MQTT publish failed for "
                        "device %s after %d attempts: %s",
                        device_id,
                        MQTT_RETRIES,
                        err,
                    )

        return False

    async def publish(self) -> None:
        """Publish the current heatmap to every selected clock."""

        if not self.enabled:
            return

        async with self._publish_lock:
            payload = await self._build_payload()

            if payload is None:
                _LOGGER.debug(
                    "No valid GitHub data available "
                    "for publishing"
                )
                return

            successful = 0

            for device_id in self.device_ids:
                if await self._publish_to_device(
                    device_id,
                    payload,
                ):
                    successful += 1

            if successful:
                self.last_successful_publish = (
                    datetime.now(timezone.utc)
                )

                _LOGGER.info(
                    "GitHub Heatmap published to "
                    "%d/%d AWTRIX clock(s)",
                    successful,
                    len(self.device_ids),
                )

                # A prefix may have become available after
                # initial setup. Make sure availability is
                # subscribed now.
                await self.subscribe_availability()

            else:
                _LOGGER.warning(
                    "GitHub Heatmap could not be published "
                    "to any selected AWTRIX clock"
                )

    # ------------------------------------------------------------------
    # Automatic updates
    # ------------------------------------------------------------------

    def start_auto_publish(self) -> None:
        """Start publishing after successful coordinator updates."""

        if self._update_listener_unsub is None:
            self._update_listener_unsub = (
                self.async_add_listener(
                    self._coordinator_updated
                )
            )

        self._auto_publish = True

    @callback
    def _coordinator_updated(self) -> None:
        """Publish after a successful GitHub refresh."""

        if not self._auto_publish:
            return

        if not self.enabled:
            return

        if not self.last_update_success:
            # DataUpdateCoordinator retains the previous
            # successful data. Do not overwrite the display.
            _LOGGER.debug(
                "GitHub refresh failed; keeping "
                "last successfully published heatmap"
            )
            return

        self.hass.async_create_task(
            self.publish()
        )

    async def async_refresh_and_publish(
        self,
    ) -> None:
        """Force a GitHub refresh and publish."""

        if not self.enabled:
            return

        await self.async_request_refresh()

        if (
            self.last_update_success
            and self.data
        ):
            await self.publish()
        else:
            _LOGGER.warning(
                "Manual GitHub refresh failed; "
                "existing AWTRIX display was retained"
            )

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    async def subscribe_availability(self) -> None:
        """Subscribe to availability for all selected clocks."""

        await self.unsubscribe_availability()

        for device_id in self.device_ids:
            topic = self.availability_topic(
                device_id
            )

            if not topic:
                continue

            @callback
            def availability_received(
                msg,
                selected_device_id=device_id,
            ) -> None:
                payload = (
                    msg.payload
                    if isinstance(
                        msg.payload,
                        str,
                    )
                    else msg.payload.decode(
                        errors="ignore"
                    )
                ).strip().lower()

                previous = (
                    self._last_availability.get(
                        selected_device_id
                    )
                )

                self._last_availability[
                    selected_device_id
                ] = payload

                if (
                    payload == "online"
                    and previous != "online"
                ):
                    self.hass.async_create_task(
                        self._republish_device(
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
                "Subscribed to AWTRIX availability "
                "for device %s",
                device_id,
            )

    async def unsubscribe_availability(
        self,
    ) -> None:
        """Unsubscribe from all availability topics."""

        for unsub in self._availability_unsubs:
            try:
                unsub()
            except Exception:
                _LOGGER.debug(
                    "Failed to unsubscribe from "
                    "AWTRIX availability",
                    exc_info=True,
                )

        self._availability_unsubs.clear()

    async def _republish_device(
        self,
        device_id: str,
    ) -> None:
        """Republish to one AWTRIX after it comes online."""

        if not self.enabled:
            return

        await asyncio.sleep(2)

        async with self._publish_lock:
            payload = await self._build_payload()

            if payload is None:
                return

            if await self._publish_to_device(
                device_id,
                payload,
            ):
                _LOGGER.info(
                    "GitHub Heatmap republished to "
                    "AWTRIX device %s after reconnect",
                    device_id,
                )

    # ------------------------------------------------------------------
    # Removal / shutdown
    # ------------------------------------------------------------------

    async def remove(self) -> None:
        """Remove GitHub Heatmap from every selected clock."""

        for device_id in self.device_ids:
            topic = self.app_topic(
                device_id
            )

            if not topic:
                continue

            for attempt in range(
                1,
                MQTT_RETRIES + 1,
            ):
                try:
                    await mqtt.async_publish(
                        self.hass,
                        topic,
                        "",
                        qos=0,
                        retain=False,
                    )
                    break

                except Exception as err:
                    if attempt < MQTT_RETRIES:
                        await asyncio.sleep(
                            MQTT_RETRY_DELAY
                            * 2 ** (
                                attempt - 1
                            )
                        )
                    else:
                        _LOGGER.warning(
                            "Could not remove GitHub Heatmap "
                            "from AWTRIX device %s: %s",
                            device_id,
                            err,
                        )

    async def async_shutdown(
        self,
    ) -> None:
        """Stop coordinator and remove pushed apps."""

        self._auto_publish = False

        if self._update_listener_unsub:
            self._update_listener_unsub()
            self._update_listener_unsub = None

        await self.unsubscribe_availability()
        await self.remove()
