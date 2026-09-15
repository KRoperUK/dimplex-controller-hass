---
description: Sign the Dimplex Hub integration into the Dimplex cloud with email and password, or with an OAuth code captured from a browser.
---

# Connect your account

The integration signs in to the Dimplex cloud on your behalf and stores the resulting
tokens in the config entry. There are two ways to get those tokens.

| Method               | Use it when                                                       | Trade-off                                          |
| -------------------- | ----------------------------------------------------------------- | -------------------------------------------------- |
| **Email / password** | Default choice.                                                   | Your Dimplex password is stored in Home Assistant. |
| **Manual auth code** | Password login fails, or you would rather not store the password. | More steps, and the code expires within minutes.   |

Both end up with the same tokens, and both refresh automatically afterwards.

## Sign in

=== "Email / password"

    1. Select **Email / password (recommended)**.
    2. Enter your Dimplex cloud account email and password.
    3. Click **Submit**.

    The integration performs the login itself and keeps only the tokens plus your email
    address. See [what is stored](../reference/options.md#what-is-stored).

=== "Manual auth code"

    1. Select **Manual auth code from browser**.
    2. Copy the login URL shown in the dialog and open it in a new browser tab.
    3. **Before logging in**, open developer tools with ++f12++ and switch to the
       **Network** tab.
    4. Enable **Preserve log** — without it the final request disappears before you can
       read it.
    5. Log in with your Dimplex credentials.
    6. The final redirect fails with "cannot open page". This is expected.
    7. In the Network tab, find the last request whose URL contains `?code=…`.
    8. Copy the whole redirect URL, or just the `code` value.
    9. Paste it into **Redirect URL or code** and click **Submit**.

    !!! warning "Codes expire quickly"

        An auth code is valid for a matter of minutes and is single-use. If setup rejects
        it, capture a fresh one rather than reusing the same value.

    If your account has MFA enabled, complete the MFA challenge in the browser *before*
    copying the redirect URL.

## Re-authenticating

If the stored tokens expire or are rejected, the integration raises Home Assistant's
built-in reauthentication flow and a repair notification that links straight to it.

1. Go to **Settings** → **Devices & services**.
2. Find **Dimplex Hub** and click **Reconfigure** / **Re-authenticate**.
3. Choose either method above, exactly as during initial setup.

Azure B2C refresh tokens last around 90 days, so a prompt every few months is normal. Being
asked repeatedly is not — see
[tokens keep expiring](../help/troubleshooting.md#tokens-keep-expiring).

## More than one account

You can add the integration more than once; each entry is a separate cloud session with its
own tokens and its own entities. See [multi-account](../internals/multi-account.md).

## Next

- [Check the install worked](index.md#check-it-worked)
- [Options](../reference/options.md) — polling and platform toggles
- [Troubleshooting](../help/troubleshooting.md) — if setup failed
