"""Turn adapter exceptions into errors a user can act on.

The API adapter raises :class:`InvalidAuth`, :class:`ControlRejected` (the cloud
refused this control for this appliance) or :class:`CannotConnect` (the request did
not get through). Home Assistant renders an unhandled exception from a service call
or an entity method as a generic failure with a traceback, which is how
dimplex-controller-hass#149 was reported — "failed to perform … unknown error".

The three cases get deliberately different wording, because the user's next step
differs: authentication needs re-linking, a refusal will never succeed for that
appliance, and a connection failure may work on the next try.

Shared so every caller behaves the same. Previously only the climate entity
translated these, leaving switch toggles and every ``dimplex.*`` action to surface
raw adapter exceptions.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from homeassistant.exceptions import HomeAssistantError

from .api import CannotConnect, ControlRejected, InvalidAuth


@contextmanager
def control_errors(target: str) -> Iterator[None]:
    """Re-raise Dimplex control failures as a clear :class:`HomeAssistantError`.

    ``target`` names what the user was acting on — an appliance name, or an action
    name when no appliance is resolvable — and is quoted back in the message.

    ``ControlRejected`` must be caught before ``CannotConnect``: it is a subclass,
    so the order matters.
    """
    try:
        yield
    except InvalidAuth as err:
        raise HomeAssistantError(f"Dimplex authentication failed while controlling {target}.") from err
    except ControlRejected as err:
        raise HomeAssistantError(
            f"The Dimplex cloud rejected this control for {target}. The appliance may not "
            "support it remotely — some Quantum storage heaters reject off/setpoint "
            "changes — so retrying will not help."
        ) from err
    except CannotConnect as err:
        raise HomeAssistantError(
            f"Could not reach the Dimplex cloud to control {target}. The service may be "
            "temporarily unavailable; nothing was changed."
        ) from err
