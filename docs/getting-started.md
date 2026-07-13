# Getting started

This guide walks you through installing and configuring the Dimplex Hub integration for Home Assistant.

## Prerequisites

- A working Home Assistant installation (2023.1 or later recommended).
- A Dimplex cloud account with at least one registered appliance.
- Internet access from your Home Assistant instance.

## Installation

### Via HACS (recommended)

1. Open **HACS** in Home Assistant.
2. Search for **Dimplex Hub**.
3. Click **Download**.
4. Restart Home Assistant.
5. Go to **Settings** > **Devices & Services** > **Add Integration** and search for **Dimplex Hub**.

Install the **stable** channel for everyday use. Pre-releases (`vX.Y.Z-rc.N` release candidates and `vX.Y.Z-pr.*` PR builds) are optional for testers — enable them in HACS only if you intend to dogfood unreleased code. See [Pre-releases and update entity](troubleshooting.md#hacs-shows-an-update-after-installing-a-pre-release).

### Manual installation

1. Open your Home Assistant configuration directory.
2. Create `custom_components` if it does not already exist.
3. Copy `custom_components/dimplex` from this repository into your Home Assistant config.
4. Restart Home Assistant.
5. Go to **Settings** > **Devices & Services** > **Add Integration** and search for **Dimplex Hub**.

## First-time setup

1. In Home Assistant, go to **Settings** > **Devices & Services**.
2. Click **+ Add Integration**.
3. Search for **Dimplex Hub** and select it.
4. Choose your authentication method (see below).
5. Follow the on-screen prompts to complete the setup.

## Authentication methods

### Email / password (recommended)

1. Select **Email / password (recommended)**.
2. Enter your Dimplex cloud account email and password.
3. Click **Submit**.

The integration signs in on your behalf and stores the resulting tokens securely in the config entry.

### Manual auth code

Use this method if the email/password flow fails, or if you prefer not to enter your credentials in Home Assistant.

1. Select **Manual auth code from browser**.
2. Copy the login URL shown in the integration dialog.
3. Open it in a new browser tab.
4. Open Developer Tools (`F12`) and go to the **Network** tab.
5. Enable **Preserve log**.
6. Log in with your Dimplex credentials.
7. The final redirect will fail — this is expected.
8. Find the last request that contains `?code=...` in its URL.
9. Copy the full redirect URL or just the `code` value.
10. Paste it into the integration's **Redirect URL or code** field.
11. Click **Submit**.

> **Tip:** Auth codes are short-lived. If the code expires, repeat the steps and capture a fresh one.

## Verifying the installation

After setup completes:

1. Go to **Settings** > **Devices & Services**.
2. Find **Dimplex Hub** in the list.
3. Click on it to see your configured entities.
4. Go to **Settings** > **Devices & Services** > **Entities** and search for `dimplex` to see all entities.

You should see sensors for room temperature, binary sensors for comfort status, and switches for EcoStart — one set per appliance.

## What next?

- Read the [configuration guide](configuration.md) for options flow and platform toggles.
- Browse the [entities reference](entities.md) to understand what each entity does.
- Check [troubleshooting](troubleshooting.md) if you hit problems.
