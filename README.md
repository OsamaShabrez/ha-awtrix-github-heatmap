# AWTRIX NG GitHub Heatmap

Display your GitHub contribution activity on an **AWTRIX NG clock through Home Assistant**.

The integration fetches your contribution history, renders a compact 365-day heatmap for the AWTRIX NG 32×8 display, and publishes it over MQTT.

## Features

- 📊 365-day GitHub contribution heatmap
- 🖥️ Multiple AWTRIX NG clocks
- 👤 GitHub avatar display
- 🔄 Configurable refresh interval
- 💾 Avatar caching
- 📡 Per-clock MQTT handling
- ⚡ Automatic recovery when a clock comes back online
- 🚫 Automatic app cleanup when disabled or a clock is removed
- 🔄 Manual refresh service
- 📈 Home Assistant status information
- 👥 Multiple GitHub accounts through separate integration entries

## Installation

### HACS

[![Open your Home Assistant instance and show the integration page.](https://my.home-assistant.io/badges/integration.svg)](https://my.home-assistant.io/redirect/integration/?domain=github_heatmap)

If the repository is not yet available in the HACS default repository list, add it as a custom repository:

1. Open **HACS → Integrations**
2. Open the **⋮** menu
3. Select **Custom repositories**
4. Add `https://github.com/OsamaShabrez/ha-awtrix-github-heatmap`
5. Select **Integration**
6. Install **AWTRIX NG GitHub Heatmap**

Then add **GitHub Heatmap** from:

**Settings → Devices & services → Add integration**

## Configuration

| Option               | Description                   |
| -------------------- | ----------------------------- |
| **GitHub username**  | GitHub account to display     |
| **AWTRIX clocks**    | One or more AWTRIX NG clocks  |
| **Refresh interval** | Contribution refresh interval |
| **Enabled**          | Enable or disable the heatmap |

Each integration entry represents one GitHub account. Multiple accounts can be configured using separate entries.

## Display

The heatmap is rendered for the AWTRIX NG **32×8 matrix**, with the GitHub avatar displayed alongside the contribution calendar.

The avatar is cached, so it is not downloaded on every contribution refresh.

## Reliability

The integration is designed to handle temporary connectivity problems without unnecessarily clearing the display.

- GitHub API failures retain the last valid data.
- MQTT failures are handled independently per clock.
- Offline clocks are updated automatically when they return.
- Adding a clock publishes the current heatmap.
- Removing a clock removes the app from that clock.
- Disabling the integration removes the app from the selected clocks.

No separate Home Assistant automation is required for cleanup.

## Manual refresh

The integration provides the `github_heatmap.refresh` action:

```yaml
action: github_heatmap.refresh
```

This immediately refreshes the contribution data and republishes the heatmap to the selected clocks.

## GitHub data

Contribution data is provided by the [GitHub Contributions API](https://github.com/grubersjoe/github-contributions-api).

The integration uses the upstream API's last-year contribution dataset.

## Support

When reporting an issue, include:

- Home Assistant version
- GitHub Heatmap version
- AWTRIX NG firmware version
- Number of configured clocks
- Relevant Home Assistant or MQTT logs

Remove credentials, tokens, passwords, and other sensitive information before posting logs.

## Credits

This project was inspired by and uses the **[GitHub Contributions API](https://github.com/grubersjoe/github-contributions-api)** created by **[grubersjoe](https://github.com/grubersjoe)**.

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE).
