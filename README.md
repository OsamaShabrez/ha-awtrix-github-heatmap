# AWTRIX NG GitHub Heatmap

Display your **GitHub contribution activity directly on an AWTRIX NG clock through Home Assistant**.

The integration fetches the last 365 days of GitHub contribution data, renders it into the AWTRIX NG's **32×8 pixel matrix**, and publishes it as a native AWTRIX pushed app.

> **Home Assistant custom integration · AWTRIX NG · HACS-ready**

## ✨ Features

- 📊 **365-day GitHub contribution heatmap**
- 🖥️ **AWTRIX NG 32×8 matrix rendering**
- 👤 **GitHub avatar displayed as an 8×8 panel**
- 🔄 Configurable automatic refresh interval
- 🕐 Avatar caching to avoid unnecessary downloads
- 🖥️ **Multiple AWTRIX NG clocks**
- 👤 One GitHub account per integration entry
- 🔀 Multiple integration entries can be created for different GitHub accounts
- ⚡ Automatically republishes when an AWTRIX clock comes back online
- 🚫 Disabling the integration removes the `github_heatmap` app from selected clocks
- 🔄 Changing the selected clocks immediately applies the new configuration
- 🧹 Removing a clock from the configuration removes the app from that clock
- 🔁 Failed GitHub requests are retried
- 📡 Failed MQTT publishes are retried
- 🛡️ Temporary GitHub/MQTT failures do not intentionally destroy the last valid display
- 🧪 Manual refresh through the Home Assistant `github_heatmap.refresh` service
- 📈 Home Assistant sensors for contribution count and update/publish status
- 🎨 Fixed GitHub-style contribution colors
- 🌈 Rainbow months: **off**
- 📅 Month splitting: **off**
- 🎯 Avatar: **on**

---

## 🖼️ What it displays

The AWTRIX matrix is divided into two areas:

```text
┌────────┬─┬──────────────────────────┐
│        │ │                          │
│ AVATAR │ │     CONTRIBUTION         │
│  8×8   │ │       HEATMAP            │
│        │ │                          │
│        │ │                          │
└────────┴─┴──────────────────────────┘
   8 px    1 px        23 px
```

The avatar occupies the first **8×8 pixels**, followed by a one-pixel separator. The remaining matrix area displays the newest available contribution weeks.

The renderer preserves the column-major pixel representation required internally before converting the final bitmap to AWTRIX's row-major representation.

---

## 🔌 How it works

The integration runs entirely inside Home Assistant.

```text
┌──────────────────────┐
│      GitHub          │
│ contribution profile │
└──────────┬───────────┘
           │
           │ HTTPS
           ▼
┌────────────────────────────┐
│ github-contributions-api   │
│        jogruber.de         │
└────────────┬───────────────┘
             │
             │ contribution data
             ▼
┌────────────────────────────┐
│     Home Assistant         │
│                            │
│  GitHub Heatmap            │
│  ├─ fetch data             │
│  ├─ cache avatar           │
│  ├─ render 32×8 bitmap     │
│  └─ publish MQTT           │
└────────────┬───────────────┘
             │
             │ MQTT
             ▼
┌────────────────────────────┐
│        AWTRIX NG           │
│                            │
│   github_heatmap app       │
└────────────────────────────┘
```

The integration dynamically obtains the MQTT prefix from the selected AWTRIX NG device's Home Assistant MQTT prefix sensor rather than hardcoding a clock name or MQTT prefix.

This allows the same integration to work with multiple AWTRIX NG clocks.

---

## 📡 GitHub data source

This project uses the excellent **GitHub Contributions API v4** created by [@grubersjoe](https://github.com/grubersjoe):

**https://github.com/grubersjoe/github-contributions-api**

The API scrapes GitHub's contribution profile and exposes the contribution history as structured JSON containing:

- contribution totals
- individual dates
- contribution counts
- contribution levels

The API supports requesting GitHub's "last year" view using:

```text
?y=last
```

This project therefore uses:

```text
https://github-contributions-api.jogruber.de/v4/<USERNAME>?y=last
```

The API documentation states that results are cached for approximately one hour and exposes both yearly totals and daily contribution data.

### Why this API?

The original motivation was to reproduce the contribution heatmap visible on GitHub without requiring a GitHub OAuth flow or a GitHub token inside Home Assistant.

This is particularly useful because GitHub's contribution graph can contain activity that is difficult to reproduce reliably through the standard GitHub REST API alone.

**Credit:** This project would not exist in its current form without the work behind `github-contributions-api` by [grubersjoe](https://github.com/grubersjoe).

Please see the upstream project for its implementation, limitations, caching behavior, and licensing.

---

## 🏠 Home Assistant integration

This project is implemented as a native Home Assistant custom integration.

The integration lives under:

```text
custom_components/github_heatmap/
```

and is designed to be installed and updated through **HACS**.

HACS requires integration files to be located under `custom_components/<integration_domain>/` and requires the integration manifest to contain the appropriate metadata.

### Configuration

After installation:

**Settings → Devices & services → Add integration → GitHub Heatmap**

Configure:

| Setting | Description |
|---|---|
| **GitHub username** | GitHub account whose contribution graph is displayed |
| **AWTRIX clocks** | One or more AWTRIX NG clocks |
| **Refresh interval** | How often GitHub data is fetched |
| **Enabled** | Enable/disable the AWTRIX app |

The GitHub account is intentionally **one account per integration entry**.

If multiple accounts are required, simply create another GitHub Heatmap integration entry.

Multiple clocks can be selected for each entry.

---

## 🔄 Configuration behavior

The integration is designed so that configuration itself controls the AWTRIX app lifecycle.

### Enabled → OFF

The integration removes:

```text
github_heatmap
```

from every selected AWTRIX clock.

No separate Home Assistant automation is required.

### Enabled → ON

The integration fetches the current GitHub data and republishes the application.

### Clock removed

If a clock is removed from the selected-device configuration, the integration removes the `github_heatmap` app from that clock.

### Clock added

The newly selected clock receives the application immediately after the configuration reload.

### Refresh interval changed

The coordinator is recreated with the new interval and starts using the new schedule.

---

## 🔁 Automatic refresh

The integration uses Home Assistant's `DataUpdateCoordinator`.

The normal flow is:

```text
Timer
  ↓
GitHub API
  ↓
Contribution data updated
  ↓
Renderer
  ↓
MQTT publish
  ↓
AWTRIX
```

The existing rendered display is not deliberately removed when a temporary GitHub request fails.

This prevents a transient API failure from unnecessarily blanking the clock.

---

## 📡 AWTRIX availability

Each selected AWTRIX clock is handled independently.

When an AWTRIX clock reports itself as offline, the integration does not remove the application's configuration from the integration.

When that clock returns online:

```text
AWTRIX offline
      ↓
AWTRIX comes online
      ↓
wait briefly for device readiness
      ↓
rebuild current bitmap
      ↓
publish github_heatmap
```

This is handled independently for each selected clock.

---

## 👤 Avatar

The GitHub avatar is permanently enabled.

The avatar is rendered into an **8×8 pixel image**.

It is cached inside the integration rather than downloaded every contribution refresh.

The current cache lifetime is:

```text
24 hours
```

Therefore a normal contribution refresh does not cause another avatar download.

---

## 🎨 Rendering

The current configuration intentionally keeps:

```text
Rainbow months: OFF
Month split:    OFF
Avatar:         ON
```

The heatmap uses five contribution levels:

```text
Level 0 → 0x161B22
Level 1 → 0x0E4429
Level 2 → 0x006D32
Level 3 → 0x26A641
Level 4 → 0x39D353
```

The contribution data is transformed into the AWTRIX NG matrix representation and validated to ensure the final bitmap contains exactly:

```text
32 × 8 = 256 pixels
```

---

## 🛠️ Manual refresh

A Home Assistant service is provided:

```yaml
action: github_heatmap.refresh
```

This forces the integration to:

1. Fetch the latest GitHub contribution data.
2. Render the heatmap.
3. Publish it to all selected AWTRIX clocks.

Useful for testing configuration changes without waiting for the normal refresh interval.

---

## 📊 Home Assistant entities

The integration exposes status information including:

### Contributions

The GitHub contribution total for the requested last-year period.

### Last Update

Timestamp of the last successful GitHub data update.

### Last Publish

Timestamp of the last successful AWTRIX MQTT publication.

These provide simple visibility into whether the integration is operating normally.

---

## 🧯 Error handling

The integration is designed around transient failures being recoverable.

### GitHub

Failed API requests are retried.

If the refresh still fails, the previously successful coordinator data remains available rather than deliberately replacing the clock display with an empty heatmap.

### MQTT

MQTT publication is retried independently.

A failure on one AWTRIX clock does not prevent publication attempts to other selected clocks.

### AWTRIX availability

Individual clocks are tracked independently so one offline device does not prevent the integration from serving other clocks.

---

## 📦 Installation

### HACS

Once available through HACS:

1. Open **HACS**.
2. Search for **AWTRIX NG GitHub Heatmap**.
3. Install the integration.
4. Restart Home Assistant if requested.
5. Add **GitHub Heatmap** from **Settings → Devices & services**.

### Custom repository

During development, the repository can be added to HACS as a custom repository.

Repository:

```text
https://github.com/OsamaShabrez/ha-awtrix-github-heatmap
```

Select:

```text
Integration
```

HACS supports installing public GitHub repositories as custom repositories when they follow the expected repository structure.

---

## 🧑‍💻 Development

Repository:

**https://github.com/OsamaShabrez/ha-awtrix-github-heatmap**

Project structure:

```text
ha-awtrix-github-heatmap/
├── custom_components/
│   └── github_heatmap/
│       ├── __init__.py
│       ├── config_flow.py
│       ├── const.py
│       ├── coordinator.py
│       ├── manifest.json
│       ├── renderer.py
│       ├── sensor.py
│       ├── services.yaml
│       └── translations/
│           └── en.json
├── .github/
│   └── workflows/
│       └── hacs.yml
├── hacs.json
├── README.md
└── LICENSE
```

The repository uses GitHub Actions for automated HACS/Home Assistant validation.

---

## 🚧 Project status

This project is currently under active development.

The integration has been built specifically around:

- Home Assistant
- AWTRIX NG
- MQTT
- GitHub contribution activity
- HACS distribution

The architecture is intentionally kept as a Home Assistant integration rather than requiring a separate Cloudflare Worker or external application.

### Current goals

- Reliable AWTRIX publishing
- Multiple AWTRIX clocks
- Automatic recovery
- Minimal configuration
- HACS distribution
- Safe configuration updates
- Maintainable Home Assistant-native implementation

---

## 🙏 Credits

### GitHub Contributions API

Major inspiration and the contribution-data API used by this project:

**[grubersjoe/github-contributions-api](https://github.com/grubersjoe/github-contributions-api)**

The upstream project provides the API used to retrieve GitHub contribution history.

### Home Assistant

Built as a custom Home Assistant integration using Home Assistant's integration and config-flow architecture.

### HACS

Designed for distribution through the **Home Assistant Community Store**. HACS provides the installation, update, and repository-management infrastructure for custom Home Assistant integrations.

---

## 📄 License

See [`LICENSE`](LICENSE) for the license applicable to this project.

The upstream `github-contributions-api` project has its own license and terms; refer to the upstream repository for those details.

---

## ⭐ Contributing

Issues, bug reports, improvements, and pull requests are welcome.

If you encounter a problem, please include:

- Home Assistant version
- Integration version
- AWTRIX NG firmware version
- Number of configured clocks
- Relevant Home Assistant logs
- MQTT-related logs where applicable

Please avoid posting GitHub credentials, MQTT credentials, or other secrets in issues.