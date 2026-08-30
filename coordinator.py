from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from datetime import datetime, timezone
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
    """Fetch GitHub contributions and publish them to AWTRIX."""

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        device_ids: list[str],
        refresh_minutes: int,
        avatar_contrast: float = 1.0,
        enabled: bool = True,
        entry_id: str | None = None,
    ) -> None:
        self.username = username
        self.device_ids = device_ids
        self.refresh_minutes = refresh_minutes
        self.avatar_contrast = avatar_contrast
        self.enabled = enabled
        self.entry_id = entry_id

        self.last_successful_update: datetime | None = None

        self._availability_unsubs: list = []
        self._last_availability: dict[str, str] = {}

        self._avatar_pixels: list[int] | None = None
        self._avatar_url: str | None = None
        self._avatar_fetched_at: float | None = None

        self._auto_publish = False
        self._update_listener_unsub = None
        self._publish_lock = asyncio.Lock()

        super().__init__(
            hass,
            _LOGGER,
            name=f"GitHub Heatmap - {username}",
            update_interval=timedelta(
                minutes=refresh_minutes
            ),
        )

    # ------------------------------------------------------------------
    # MQTT prefix / topic handling
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

            if not (
                entity_id.endswith("_mqtt_prefix")
                or "mqtt prefix" in state_name
            ):
                continue

            value = state.state.strip()

            if value and value.lower() not in (
                "unknown",
                "unavailable",
                "none",
            ):
                return value

        _LOGGER.debug(
            "Could not find MQTT prefix sensor for "
            "AWTRIX device %s",
            device_id,
        )

        return None

    def mqtt_prefix(
        self,
        device_id: str,
    ) -> str | None:
        """Return MQTT prefix for a device."""

        return self._mqtt_prefix_for_device(
            device_id
        )

    def app_topic(
        self,
        device_id: str,
    ) -> str | None:
        """Return pushed-app MQTT topic."""

        prefix = self.mqtt_prefix(device_id)

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
        """Return AWTRIX availability topic."""

        prefix = self.mqtt_prefix(device_id)

        if not prefix:
            return None

        return f"{prefix}/availability"

    async def async_wait_for_mqtt_prefixes(
        self,
        timeout: int = 30,
    ) -> bool:
        """Wait for all selected AWTRIX MQTT prefixes."""

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
                _LOGGER.debug(
                    "Resolved MQTT prefixes for all "
                    "selected AWTRIX devices"
                )
                return True

            _LOGGER.debug(
                "Waiting for AWTRIX MQTT entities; "
                "missing devices=%s",
                missing,
            )

            await asyncio.sleep(1)

        _LOGGER.warning(
            "Timed out waiting for MQTT prefixes; "
            "missing devices=%s",
            missing,
        )

        return False

    # ------------------------------------------------------------------
    # GitHub API
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict:
        """Fetch the last year's GitHub contributions."""

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
                    "Fetched %d GitHub contribution days; "
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
                last_error = err

                if attempt < API_RETRIES:
                    delay = 2 ** (attempt - 1)

                    _LOGGER.debug(
                        "GitHub request failed "
                        "(attempt %d/%d); retrying in %ss: %s",
                        attempt,
                        API_RETRIES,
                        delay,
                        err,
                    )

                    await asyncio.sleep(delay)

        raise UpdateFailed(
            f"Unable to fetch GitHub contributions: "
            f"{last_error}"
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
            and now - self._avatar_fetched_at
            < AVATAR_CACHE_HOURS * 3600
        ):
            return self._avatar_pixels

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
                    _LOGGER.warning(
                        "GitHub user has no avatar URL"
                    )
                    return self._avatar_pixels

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

                sized_avatar_url = (
                    f"{avatar_url}{separator}s=8"
                )

                async with session.get(
                    sized_avatar_url,
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

            if len(pixels) != 64:
                raise ValueError(
                    "Avatar conversion did not "
                    "produce 64 pixels"
                )

            self._avatar_pixels = pixels
            self._avatar_url = avatar_url
            self._avatar_fetched_at = now

            _LOGGER.debug(
                "GitHub avatar refreshed"
            )

            return pixels

        except Exception as err:
            _LOGGER.warning(
                "Failed to refresh GitHub avatar: %s",
                err,
            )

            return self._avatar_pixels

    # ------------------------------------------------------------------
    # Rendering / payload
    # ------------------------------------------------------------------

    async def _build_payload(self) -> str:
        """Build the AWTRIX bitmap payload."""

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

        bitmap = to_row_major(pixels)

        if len(bitmap) != PANEL_W * PANEL_H:
            raise ValueError(
                f"Renderer returned {len(bitmap)} pixels; "
                f"expected {PANEL_W * PANEL_H}"
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
            ]
        }

        return json.dumps(
            payload,
            separators=(",", ":"),
        )

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def _publish_to_device(
        self,
        device_id: str,
        payload: str,
    ) -> bool:
        """Publish to one AWTRIX device with retries."""

        topic = self.app_topic(device_id)

        if not topic:
            _LOGGER.warning(
                "Skipping device %s: MQTT prefix unavailable",
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

                _LOGGER.debug(
                    "Published GitHub Heatmap to "
                    "device %s",
                    device_id,
                )

                return True

            except Exception as err:
                if attempt < MQTT_RETRIES:
                    delay = (
                        MQTT_RETRY_DELAY
                        * (2 ** (attempt - 1))
                    )

                    _LOGGER.debug(
                        "MQTT publish failed for device %s "
                        "(attempt %d/%d); retrying in %ss: %s",
                        device_id,
                        attempt,
                        MQTT_RETRIES,
                        delay,
                        err,
                    )

                    await asyncio.sleep(delay)

                else:
                    _LOGGER.warning(
                        "MQTT publish failed for device %s "
                        "after %d attempts: %s",
                        device_id,
                        MQTT_RETRIES,
                        err,
                    )

        return False

    async def publish(self) -> None:
        """Render and publish to all selected devices."""

        if not self.enabled:
            return

        if not self.data:
            _LOGGER.warning(
                "Cannot publish GitHub Heatmap: "
                "no GitHub data"
            )
            return

        async with self._publish_lock:
            try:
                payload = await self._build_payload()
            except Exception:
                _LOGGER.exception(
                    "Failed to build GitHub Heatmap payload"
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
                _LOGGER.info(
                    "Published GitHub Heatmap to %d/%d "
                    "AWTRIX devices (total=%s)",
                    successful,
                    len(self.device_ids),
                    self.data.get(
                        "total",
                        {},
                    ).get("lastYear"),
                )
            else:
                _LOGGER.warning(
                    "Could not publish GitHub Heatmap "
                    "to any selected AWTRIX device"
                )

    # ------------------------------------------------------------------
    # Automatic refresh / publishing
    # ------------------------------------------------------------------

    def start_auto_publish(self) -> None:
        """Enable publishing after coordinator refreshes."""

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

        if not self._auto_publish or not self.enabled:
            return

        if not self.last_update_success:
            _LOGGER.debug(
                "GitHub refresh failed; retaining "
                "last successfully published heatmap"
            )
            return

        self.hass.async_create_task(
            self.publish()
        )

    async def async_refresh_and_publish(
        self,
    ) -> None:
        """Force a GitHub refresh and publish the result."""

        if not self.enabled:
            return

        await self.async_request_refresh()

        if self.last_update_success and self.data:
            await self.publish()
        else:
            _LOGGER.warning(
                "Manual GitHub Heatmap refresh failed; "
                "retaining existing display"
            )

    # ------------------------------------------------------------------
    # AWTRIX availability
    # ------------------------------------------------------------------

    async def subscribe_availability(self) -> None:
        """Subscribe to every selected AWTRIX availability topic."""

        await self.unsubscribe_availability()

        for device_id in self.device_ids:
            topic = self.availability_topic(device_id)

            if not topic:
                _LOGGER.warning(
                    "Cannot subscribe to availability for "
                    "device %s: MQTT prefix unavailable",
                    device_id,
                )
                continue

            @callback
            def availability_received(
                msg,
                selected_device_id=device_id,
            ) -> None:
                payload = (
                    msg.payload
                    if isinstance(msg.payload, str)
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

                _LOGGER.debug(
                    "AWTRIX device %s availability=%s",
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
                "Subscribed to AWTRIX availability: %s",
                topic,
            )

    async def unsubscribe_availability(self) -> None:
        """Unsubscribe from all availability topics."""

        for unsub in self._availability_unsubs:
            try:
                unsub()
            except Exception:
                _LOGGER.exception(
                    "Failed to unsubscribe from "
                    "AWTRIX availability"
                )

        self._availability_unsubs.clear()

    async def _handle_awtrix_online(
        self,
        device_id: str,
    ) -> None:
        """Republish when a device returns online."""

        if not self.enabled:
            return

        try:
            await asyncio.sleep(2)

            if not self.data:
                await self.async_request_refresh()

            if not self.data:
                return

            async with self._publish_lock:
                payload = await self._build_payload()

                if await self._publish_to_device(
                    device_id,
                    payload,
                ):
                    _LOGGER.info(
                        "Republished GitHub Heatmap to "
                        "AWTRIX device %s after it came online",
                        device_id,
                    )

        except Exception:
            _LOGGER.exception(
                "Failed to republish GitHub Heatmap "
                "to AWTRIX device %s",
                device_id,
            )

    # ------------------------------------------------------------------
    # Removal / shutdown
    # ------------------------------------------------------------------

    async def remove(self) -> None:
        """Remove the pushed application from all selected devices."""

        for device_id in self.device_ids:
            topic = self.app_topic(device_id)

            if not topic:
                _LOGGER.debug(
                    "Cannot remove GitHub Heatmap from "
                    "device %s: MQTT prefix unavailable",
                    device_id,
                )
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

                    _LOGGER.debug(
                        "Removed GitHub Heatmap from "
                        "AWTRIX device %s",
                        device_id,
                    )

                    break

                except Exception as err:
                    if attempt < MQTT_RETRIES:
                        await asyncio.sleep(
                            MQTT_RETRY_DELAY
                            * (2 ** (attempt - 1))
                        )
                    else:
                        _LOGGER.warning(
                            "Failed to remove GitHub Heatmap "
                            "from device %s: %s",
                            device_id,
                            err,
                        )

    async def async_shutdown(self) -> None:
        """Clean up listeners and remove the app."""

        self._auto_publish = False

        if self._update_listener_unsub:
            self._update_listener_unsub()
            self._update_listener_unsub = None

        await self.unsubscribe_availability()
        await self.remove()
