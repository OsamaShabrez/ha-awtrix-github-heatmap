from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
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
        user_input: dict | None = None,
    ):
        """Handle initial setup."""

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            device_ids = user_input[CONF_DEVICE_ID]

            if not username:
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._schema(),
                    errors={"base": "invalid_username"},
                )

            if not device_ids:
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._schema(),
                    errors={"base": "no_device"},
                )

            device_ids = sorted(set(device_ids))

            await self.async_set_unique_id(
                f"{username.lower()}:{','.join(device_ids)}"
            )

            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"GitHub Heatmap - {username}",
                data={
                    CONF_USERNAME: username,
                    CONF_DEVICE_ID: device_ids,
                },
                options={
                    CONF_USERNAME: username,
                    CONF_DEVICE_ID: device_ids,
                    CONF_REFRESH: user_input[CONF_REFRESH],
                    CONF_ENABLED: user_input[CONF_ENABLED],
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=self._schema(),
        )

    @staticmethod
    def _schema():
        """Return initial configuration schema."""

        return vol.Schema(
            {
                vol.Required(
                    CONF_USERNAME,
                ): selector.TextSelector(),

                vol.Required(
                    CONF_DEVICE_ID,
                ): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(
                        integration="mqtt",
                        multiple=True,
                    )
                ),

                vol.Required(
                    CONF_REFRESH,
                    default=DEFAULT_REFRESH,
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
                    default=DEFAULT_ENABLED,
                ): selector.BooleanSelector(),
            }
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return options flow."""

        return GitHubHeatmapOptionsFlow()


class GitHubHeatmapOptionsFlow(
    config_entries.OptionsFlowWithReload,
):
    """Handle GitHub Heatmap options."""

    async def async_step_init(
        self,
        user_input: dict | None = None,
    ):
        """Handle configuration changes."""

        current_data = self.config_entry.data
        current_options = self.config_entry.options

        username = current_options.get(
            CONF_USERNAME,
            current_data.get(CONF_USERNAME, ""),
        )

        device_ids = current_options.get(
            CONF_DEVICE_ID,
            current_data.get(CONF_DEVICE_ID, []),
        )

        if isinstance(device_ids, str):
            device_ids = [device_ids]

        refresh = current_options.get(
            CONF_REFRESH,
            DEFAULT_REFRESH,
        )

        enabled = current_options.get(
            CONF_ENABLED,
            DEFAULT_ENABLED,
        )

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()

            device_ids = sorted(
                set(user_input[CONF_DEVICE_ID])
            )

            refresh = user_input[CONF_REFRESH]
            enabled = user_input[CONF_ENABLED]

            if not username:
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._schema(
                        username,
                        device_ids,
                        refresh,
                        enabled,
                    ),
                    errors={"base": "invalid_username"},
                )

            if not device_ids:
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._schema(
                        username,
                        device_ids,
                        refresh,
                        enabled,
                    ),
                    errors={"base": "no_device"},
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
                username,
                device_ids,
                refresh,
                enabled,
            ),
        )

    @staticmethod
    def _schema(
        username: str,
        device_ids: list[str],
        refresh: int,
        enabled: bool,
    ):
        """Return options schema."""

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
