# Configuration

This page covers the configuration options available for the Dimplex Hub integration.

## Config flow

The integration uses Home Assistant's config flow, so all configuration is done through the UI. No YAML editing is required.

## Authentication options

### Email / password

The recommended method. Enter your Dimplex cloud credentials during setup.

- **Pros:** Simple, no browser needed after setup, tokens refresh automatically.
- **Cons:** Requires your Dimplex password.

### Manual auth code

Provide an OAuth authorisation code captured from a browser session.

- **Pros:** Does not require storing your Dimplex password in Home Assistant.
- **Cons:** More steps, the code expires quickly.

See [Getting started](getting-started.md) for the full manual auth code walkthrough.

## Options flow

After installation, you can enable or disable platforms:

1. Go to **Settings** > **Devices & Services**.
2. Find **Dimplex Hub** and click **Configure**.
3. Toggle the platforms you want on or off:
   - `sensor` — room temperature and energy sensors.
   - `binary_sensor` — comfort status.
   - `switch` — EcoStart toggle.
4. Click **Submit**.

Disabling a platform removes its entities from Home Assistant without deleting your config entry.

## Re-authentication

If your tokens expire, the integration will show a notification in Home Assistant prompting you to re-authenticate.

1. Go to **Settings** > **Devices & Services**.
2. Find **Dimplex Hub** and click **Fix issue** (or **Re-authenticate**).
3. Follow the same steps as the initial setup.

## Data retention

The integration stores the following in the config entry's `data` field:

| Key             | Purpose                                                  |
| --------------- | -------------------------------------------------------- |
| `refresh_token` | Long-lived token used to obtain new access tokens.       |
| `access_token`  | Short-lived token for API requests.                      |
| `expires_at`    | Unix timestamp when the access token expires.            |
| `username`      | Your Dimplex account email (email/password method only). |

Tokens are never written to plain-text files outside the Home Assistant config storage.

## Update interval

The integration polls the Dimplex cloud every **30 seconds** by default. This interval is not currently configurable.

## Behind a proxy

If your Home Assistant instance is behind a proxy, ensure the `aiohttp` session can reach the Dimplex API endpoints. The integration uses Home Assistant's default `aiohttp` session, so standard proxy configuration applies.

## Multiple accounts

You can add the integration multiple times if you have more than one Dimplex account (for example, a personal account and a family account). Each installation will appear as a separate **Dimplex Hub** entry in **Devices & Services**.

## Uninstalling

1. Go to **Settings** > **Devices & Services**.
2. Find **Dimplex Hub** and click **Delete**.
3. Confirm the deletion.

This removes the config entry and all associated entities. It does not delete your custom Lovelace cards or automations — you will need to remove those manually.
