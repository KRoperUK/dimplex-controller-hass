# Troubleshooting

This page helps you diagnose and resolve common issues with the Dimplex Hub integration.

## Setup failures

### The integration cannot connect

**Symptom:** Setup fails with a `CannotConnect` error.

**Possible causes:**

- Your Home Assistant instance has no internet access.
- The GDHV API is temporarily unavailable.
- A firewall or proxy is blocking traffic.

**Steps to resolve:**

1. Confirm your Home Assistant instance can reach the internet.
2. Check the Home Assistant logs (**Settings** > **System** > **Logs**) for details.
3. If behind a proxy, ensure `aiohttp` traffic is allowed.

### Invalid credentials

**Symptom:** Setup fails with `InvalidAuth`.

**Possible causes:**

- Incorrect email or password.
- The auth code has expired.
- The Dimplex account has MFA enabled and the code was not generated correctly.

**Steps to resolve:**

1. If using email/password, verify your credentials in the official Dimplex Control app.
2. If using a manual auth code, capture a fresh one (codes expire quickly).
3. If MFA is enabled, complete the MFA challenge in the browser before copying the redirect URL.
4. Re-run the config flow or re-authenticate from **Settings** > **Devices & Services**.

### Setup fails silently

**Symptom:** The integration does not appear after adding it.

**Steps to resolve:**

1. Restart Home Assistant.
2. Check the logs for tracebacks related to `custom_components.dimplex`.
3. Verify that the `custom_components/dimplex` folder is present in your configuration directory and contains all required files.

## Runtime issues

### Entities are unavailable

**Symptom:** Entities show as `unavailable` in Home Assistant.

**Possible causes:**

- The integration cannot reach the Dimplex cloud.
- Tokens have expired and re-authentication is required.
- Your Dimplex Hub is offline.

**Steps to resolve:**

1. Check **Settings** > **System** > **Logs** for `DimplexConnectionError` or `DimplexAuthError`.
2. If you see `DimplexAuthError`, re-authenticate from **Devices & Services**.
3. If you see `DimplexConnectionError`, verify internet connectivity from your Home Assistant instance.
4. Confirm your Hub is online in the official Dimplex Control app.

### Tokens keep expiring

**Symptom:** You are repeatedly asked to re-authenticate.

**Possible causes:**

- Refresh tokens have expired (Azure B2C refresh tokens typically last 90 days).
- Network interruptions prevent token refresh.

**Steps to resolve:**

1. Use the **Email / password** method — it handles token refresh more reliably.
2. Ensure Home Assistant has consistent internet access.
3. If tokens expire immediately, delete the integration, restart Home Assistant, and add it again.

### Energy sensor shows `unavailable` in summer

This is expected behaviour. See [Energy monitoring](index.md#energy-monitoring) in the main docs.

Metered appliances only report energy data when they are actively consuming power. During warmer months, when heating is not running, the sensor is correctly reported as `unavailable` rather than `0`.

## HACS issues

### The integration does not appear in HACS

**Possible causes:**

- You have not added the custom repository in HACS.
- The repository URL is incorrect.

**Steps to resolve:**

1. In HACS, go to **Integrations** > **Explore & Add repositories**.
2. Search for `dimplex-controller-hass` or add the URL directly: `https://github.com/kroperuk/dimplex-controller-hass`.
3. Download and restart Home Assistant.

### HACS reports an update but the update fails

**Steps to resolve:**

1. Check the Home Assistant logs for file permission errors.
2. Ensure Home Assistant has write access to the `custom_components` directory.
3. Restart Home Assistant after the update completes.

## Log analysis

### Where to find logs

1. Go to **Settings** > **System** > **Logs**.
2. Filter for `dimplex` to see integration-specific entries.

### Common log messages

| Log message                      | Meaning                           | Action                              |
| -------------------------------- | --------------------------------- | ----------------------------------- |
| `DimplexAuthError`               | Token expired or invalid.         | Re-authenticate.                    |
| `DimplexConnectionError`         | Cannot reach the API.             | Check network.                      |
| `CannotConnect`                  | HA wrapper for connection errors. | Check network and API status.       |
| `InvalidAuth`                    | HA wrapper for auth errors.       | Re-authenticate.                    |
| `Energy report returned no data` | No metered data for the window.   | Normal in summer; no action needed. |

## Still stuck?

If you cannot resolve your issue, please [open a GitHub issue](https://github.com/kroperuk/dimplex-controller-hass/issues) with:

1. Your Home Assistant version.
2. The integration version (found in `manifest.json` or HACS).
3. The relevant log entries (redact any personal information such as email addresses).
4. Steps to reproduce the problem.
5. Whether the issue happens consistently or intermittently.

The more detail you provide, the faster we can help.
