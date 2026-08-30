from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_DEVICE_ID,
    CONF_ENABLED,
    CONF_REFRESH,
    CONF_USERNAME,
    DEFAULT_ENABLED,
    DEFAULT_REFRESH,
    DOMAIN,
)


class GitHubHeatmapConfigFlow(
    config_entries.ConfigFlow,
    domain=DOMAIN,
):
    """Config flow for GitHub Heatmap."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle initial setup."""

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()

            device_ids = user_input[CONF_DEVICE_ID]

            if isinstance(device_ids, str):
                device_ids = [device_ids]

            device_ids = list(
                dict.fromkeys(device_ids)
            )

            if not username:
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._schema(
                        username=username,
                        device_ids=device_ids,
                        refresh=user_input.get(
                            CONF_REFRESH,
                            DEFAULT_REFRESH,
                        ),
                        enabled=user_input.get(
                            CONF_ENABLED,
                            DEFAULT_ENABLED,
                        ),
                    ),
                    errors={
                        "base": "invalid_username"
                    },
                )

            if not device_ids:
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._schema(
                        username=username,
                        device_ids=device_ids,
                        refresh=user_input.get(
                            CONF_REFRESH,
                            DEFAULT_REFRESH,
                        ),
                        enabled=user_input.get(
                            CONF_ENABLED,
                            DEFAULT_ENABLED,
                        ),
                    ),
                    errors={
                        "base": "no_device"
                    },
                )

            return self.async_create_entry(
                title=f"GitHub Heatmap - {username}",
                data={
                    CONF_USERNAME: username,
                    CONF_DEVICE_ID: device_ids,
                },
                options={
                    CONF_USERNAME: username,
                    CONF_DEVICE_ID: device_ids,
                    CONF_REFRESH: int(
                        user_input[CONF_REFRESH]
                    ),
                    CONF_ENABLED: bool(
                        user_input[CONF_ENABLED]
                    ),
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=self._schema(
                username="",
                device_ids=[],
                refresh=DEFAULT_REFRESH,
                enabled=DEFAULT_ENABLED,
            ),
        )

    @staticmethod
    def _schema(
        username: str,
        device_ids: list[str],
        refresh: int,
        enabled: bool,
    ) -> vol.Schema:
        """Return the configuration schema."""

        return vol.Schema(
            {
                vol.Required(
                    CONF_USERNAME,
                    default=username,
                ): selector.TextSelector(),

                vol.Required(
                    CONF_DEVICE_ID,
                    default=device_ids,
                ): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(
                        integration="mqtt",
                        multiple=True,
                    )
                ),

                vol.Required(
                    CONF_REFRESH,
                    default=refresh,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=1440,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="min",
                    )
                ),

                vol.Required(
                    CONF_ENABLED,
                    default=enabled,
                ): selector.BooleanSelector(),
            }
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow."""

        return GitHubHeatmapOptionsFlow()


class GitHubHeatmapOptionsFlow(
    config_entries.OptionsFlowWithReload,
):
    """Handle GitHub Heatmap options."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle configuration changes."""

        current_username = self.config_entry.options.get(
            CONF_USERNAME,
            self.config_entry.data.get(
                CONF_USERNAME,
                "",
            ),
        )

        current_devices = self.config_entry.options.get(
            CONF_DEVICE_ID,
            self.config_entry.data.get(
                CONF_DEVICE_ID,
                [],
            ),
        )

        if isinstance(current_devices, str):
            current_devices = [current_devices]

        current_devices = list(
            dict.fromkeys(current_devices)
        )

        current_refresh = int(
            self.config_entry.options.get(
                CONF_REFRESH,
                DEFAULT_REFRESH,
            )
        )

        current_enabled = bool(
            self.config_entry.options.get(
                CONF_ENABLED,
                DEFAULT_ENABLED,
            )
        )

        if user_input is not None:
            username = user_input[
                CONF_USERNAME
            ].strip()

            device_ids = user_input[
                CONF_DEVICE_ID
            ]

            if isinstance(device_ids, str):
                device_ids = [device_ids]

            device_ids = list(
                dict.fromkeys(device_ids)
            )

            refresh = int(
                user_input[CONF_REFRESH]
            )

            enabled = bool(
                user_input[CONF_ENABLED]
            )

            if not username:
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._schema(
                        username=username,
                        device_ids=device_ids,
                        refresh=refresh,
                        enabled=enabled,
                    ),
                    errors={
                        "base": "invalid_username"
                    },
                )

            if not device_ids:
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._schema(
                        username=username,
                        device_ids=device_ids,
                        refresh=refresh,
                        enabled=enabled,
                    ),
                    errors={
                        "base": "no_device"
                    },
                )

            return self.async_create_entry(
                title="",
                data={
                    CONF_USERNAME: username,
                    CONF_DEVICE_ID: device_ids,
                    CONF_REFRESH: refresh,
                    CONF_ENABLED: enabled,
                },
            )

        return self.async_show_form(
            step_id="init",
            data_schema=self._schema(
                username=current_username,
                device_ids=current_devices,
                refresh=current_refresh,
                enabled=current_enabled,
            ),
        )

    @staticmethod
    def _schema(
        username: str,
        device_ids: list[str],
        refresh: int,
        enabled: bool,
    ) -> vol.Schema:
        """Return the options schema."""

        return vol.Schema(
            {
                vol.Required(
                    CONF_USERNAME,
                    default=username,
                ): selector.TextSelector(),

                vol.Required(
                    CONF_DEVICE_ID,
                    default=device_ids,
                ): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(
                        integration="mqtt",
                        multiple=True,
                    )
                ),

                vol.Required(
                    CONF_REFRESH,
                    default=refresh,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=1440,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="min",
                    )
                ),

                vol.Required(
                    CONF_ENABLED,
                    default=enabled,
                ): selector.BooleanSelector(),
            }
        )
