"""Diagnostics support for Dimplex Hub (redacted)."""

from __future__ import annotations

import hashlib
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from dimplex_controller import ApplianceModeFlag
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .capabilities import capabilities_for_row
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_USERNAME,
    VERSION,
)

TO_REDACT = {
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_PASSWORD,
    CONF_USERNAME,
    "access_token",
    "refresh_token",
    "password",
    "username",
    "email",
    "PrimaryUserEmail",
    "SecurityCode",
}


def _hash_identifier(value: str | None) -> str | None:
    if not value:
        return None
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return digest[:12]


def _model_snapshot(obj: Any) -> dict[str, Any] | None:
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        try:
            dumped = obj.model_dump(mode="json")
        except Exception:
            dumped = None
        if isinstance(dumped, dict):
            return dict(dumped)
    data: dict[str, Any] = {}
    for key in dir(obj):
        if key.startswith("_"):
            continue
        try:
            value = getattr(obj, key)
        except Exception:
            continue
        if callable(value):
            continue
        if isinstance(value, str | int | float | bool) or value is None:
            data[key] = value
    return data


def _iso_or_none(value: Any) -> Any:
    if value is None:
        return None
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        return iso()
    return value


def _energy_meta(energy_data: dict[str, Any] | None) -> dict[str, Any]:
    """Summarise energy series without dumping full history."""
    energy = (energy_data or {}).get("energy") or {}
    meta: dict[str, Any] = {}
    for hub_id, registers in energy.items():
        hub_meta: dict[str, Any] = {}
        for register, by_app in (registers or {}).items():
            reg_meta: dict[str, Any] = {}
            for app_id, points in (by_app or {}).items():
                count = len(points or [])
                window_start: Any = None
                window_end: Any = None
                if points:
                    timestamps = [p[0] for p in points if p and p[0] is not None]
                    if timestamps:
                        window_start = min(timestamps)
                        window_end = max(timestamps)
                reg_meta[app_id] = {
                    "point_count": count,
                    "window_start": _iso_or_none(window_start),
                    "window_end": _iso_or_none(window_end),
                }
            hub_meta[register] = reg_meta
        meta[hub_id] = hub_meta
    return meta


def _lib_version() -> str | None:
    try:
        return version("dimplex-controller")
    except PackageNotFoundError:
        return None


def _active_modes(status: Any) -> list[str] | None:
    """Decode ``ApplianceModes`` into readable mode names.

    The raw bitfield is already in the status snapshot, but nobody reading a
    diagnostics download should have to decode it by hand — that is how a
    mode-mapping bug goes unnoticed (#163).
    """
    if status is None:
        return None
    modes = getattr(status, "ApplianceModes", None)
    if modes is None:
        return None
    try:
        flags = ApplianceModeFlag(int(modes))
    except (TypeError, ValueError):
        return None
    return [member.name for member in ApplianceModeFlag if member.value and member in flags and member.name]


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime = getattr(entry, "runtime_data", None)
    status_data = getattr(getattr(runtime, "status", None), "data", None) or {}
    energy_data = getattr(getattr(runtime, "energy", None), "data", None) or {}
    status_coord = getattr(runtime, "status", None)
    energy_coord = getattr(runtime, "energy", None)

    hubs_out: list[dict[str, Any]] = []
    for hub in status_data.get("hubs") or []:
        snap = _model_snapshot(hub) or {}
        email = snap.pop("PrimaryUserEmail", None) or getattr(hub, "PrimaryUserEmail", None)
        snap.pop("SecurityCode", None)
        hubs_out.append(
            {
                "hub_id": getattr(hub, "HubId", None),
                "name": getattr(hub, "FriendlyName", None) or getattr(hub, "Name", None),
                "connection_state": getattr(hub, "ConnectionState", None),
                "firmware": getattr(hub, "FirmwareVersion", None),
                "hub_type": getattr(hub, "HubType", None),
                "primary_user_email_hash": _hash_identifier(email if isinstance(email, str) else None),
                "raw_keys": sorted(snap.keys()),
            }
        )

    appliances_out: list[dict[str, Any]] = []
    for row in status_data.get("appliances") or []:
        appliance = row.get("appliance")
        zone = row.get("zone")
        status = row.get("status")
        hub = row.get("hub")
        product = row.get("product")
        prov = None
        if appliance is not None:
            prop = getattr(type(appliance), "automatic_provisioning", None)
            if isinstance(prop, property):
                prov = appliance.automatic_provisioning
            else:
                prov = getattr(appliance, "automatic_provisioning", None)
        appliances_out.append(
            {
                "appliance_id": getattr(appliance, "ApplianceId", None),
                "friendly_name": getattr(appliance, "FriendlyName", None),
                "model": getattr(appliance, "ApplianceModel", None),
                "type": getattr(appliance, "ApplianceType", None),
                "firmware": getattr(appliance, "FirmwareVersion", None),
                "zone_name": getattr(zone, "ZoneName", None),
                "hub_id": getattr(hub, "HubId", None),
                "has_status": status is not None,
                "status": _model_snapshot(status),
                "active_modes": _active_modes(status),
                "provisioning": _model_snapshot(prov),
                # The flags every control path is gated on, resolved for this
                # appliance. Docs point at this key (#199).
                "capabilities": capabilities_for_row(appliance, status, product).as_dict(),
                "product_model": getattr(product, "ProductModelName", None),
                "product_type": getattr(product, "ProductTypeName", None),
            }
        )

    payload: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "domain": entry.domain,
            "version": entry.version,
            "options": dict(entry.options),
            "data": async_redact_data(dict(entry.data), TO_REDACT),
        },
        "versions": {
            "integration": VERSION,
            "manifest": entry.domain,
            "dimplex_controller": _lib_version(),
        },
        "coordinators": {
            "status": {
                "last_update_success": getattr(status_coord, "last_update_success", None),
                "last_exception": str(getattr(status_coord, "last_exception", None) or "") or None,
                "update_interval": str(getattr(status_coord, "update_interval", None)),
            },
            "energy": {
                "last_update_success": getattr(energy_coord, "last_update_success", None),
                "last_exception": str(getattr(energy_coord, "last_exception", None) or "") or None,
                "update_interval": str(getattr(energy_coord, "update_interval", None)),
            },
        },
        "hubs": hubs_out,
        "appliances": appliances_out,
        "energy_summary": _energy_meta(energy_data),
    }
    return async_redact_data(payload, TO_REDACT)
