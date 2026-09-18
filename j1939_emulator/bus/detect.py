"""python-can hardware discovery — Real vs Virtual emulation modes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from j1939_emulator.bus.libusb_setup import ensure_libusb_backend

ensure_libusb_backend()

import can
from can.interfaces import VALID_INTERFACES


class EmulationMode(str, Enum):
    REAL = "real"
    VIRTUAL = "virtual"


_SLOW_OR_NOISY = frozenset({"socketcand", "udp_multicast"})

# Curated probe set — scanning all VALID_INTERFACES prints missing-DLL noise.
_REAL_PROBE_INTERFACES = frozenset(
    {
        "candle",
        "gs_usb",
        "vector",
        "pcan",
        "slcan",
        "serial",
    }
)

_STRIP_KEYS = frozenset(
    {
        "vector_channel_config",
        "label",
        "uid",
        "kind",
    }
)

VIRTUAL_CHANNELS = ("vcan0", "vcan1", "vcan2")


@dataclass
class DetectedChannel:
    """One selectable channel returned by discovery."""

    uid: str
    label: str
    interface: str
    bus_kwargs: dict[str, Any] = field(default_factory=dict)
    kind: EmulationMode = EmulationMode.REAL


def _safe_value(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if hasattr(v, "value") and isinstance(getattr(v, "value"), int):
        return v
    return v


def _bus_kwargs_from_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in cfg.items():
        if k in _STRIP_KEYS:
            continue
        out[k] = _safe_value(v)

    if out.get("interface") == "gs_usb":
        if out.get("index") is not None:
            out.pop("bus", None)
            out.pop("address", None)
        if "index" in out:
            out["channel"] = out["index"]

    if out.get("interface") == "vector":
        out.pop("supports_fd", None)
        out.pop("channel_index", None)

    return out


def _is_vector_virtual(cfg: dict[str, Any]) -> bool:
    """Vector driver also exposes software virtual channels (serial 100)."""
    if cfg.get("interface") != "vector":
        return False
    serial = cfg.get("serial")
    if serial == 100:
        return True
    hw_type = cfg.get("hw_type")
    name = str(hw_type)
    if "VIRTUAL" in name.upper():
        return True
    vcc = cfg.get("vector_channel_config")
    vcc_name = getattr(vcc, "name", "") if vcc is not None else ""
    return "Virtual" in str(vcc_name)


def _friendly_real_label(cfg: dict[str, Any]) -> str:
    iface = str(cfg.get("interface", "?"))
    if iface == "candle":
        channel = str(cfg.get("channel", ""))
        serial = channel.split(":")[0] if ":" in channel else channel
        short = serial[-8:] if len(serial) > 8 else serial
        return f"candleLight  (serial ...{short})"
    if iface == "gs_usb":
        idx = cfg.get("index", cfg.get("channel"))
        return f"candleLight / gs_usb  (index {idx})"
    if iface == "vector":
        vcc = cfg.get("vector_channel_config")
        name = getattr(vcc, "name", None) if vcc is not None else None
        serial = cfg.get("serial")
        ch = cfg.get("channel")
        if name:
            return f"Vector {name}  (sn {serial})"
        return f"Vector CAN{ch}  (sn {serial})"
    if iface == "pcan":
        return f"Peak/PCAN  ({cfg.get('channel')})"
    if iface == "slcan":
        return f"Serial/SLCAN  ({cfg.get('channel')})"
    return f"{iface}  ch={cfg.get('channel')}"


def _uid_real(cfg: dict[str, Any]) -> str:
    iface = cfg.get("interface")
    if iface == "candle":
        return f"candle:{cfg.get('channel')}"
    if iface == "gs_usb":
        return f"gs_usb:index={cfg.get('index', cfg.get('channel'))}"
    if iface == "vector":
        return f"vector:sn={cfg.get('serial')}:ch={cfg.get('channel')}"
    return f"{iface}:{cfg.get('channel')}:{cfg.get('serial')}"


def _dedupe_real(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prefer candle over gs_usb for the same USB sticks; drop Vector virtual."""
    candles = [c for c in raw if c.get("interface") == "candle"]
    gs = [c for c in raw if c.get("interface") == "gs_usb"]
    vectors = [
        c for c in raw if c.get("interface") == "vector" and not _is_vector_virtual(c)
    ]
    others = [
        c
        for c in raw
        if c.get("interface") not in ("candle", "gs_usb", "vector", "virtual")
    ]

    preferred_sticks = candles if candles else gs
    return preferred_sticks + vectors + others


def detect_real_hardware(timeout: float = 6.0) -> list[DetectedChannel]:
    """Physical adapters only — one entry per real CAN port."""
    import contextlib
    import io
    import logging
    import sys

    probe = set(_REAL_PROBE_INTERFACES)
    if sys.platform.startswith("linux"):
        probe.add("socketcan")
    interfaces = sorted((VALID_INTERFACES & probe) - _SLOW_OR_NOISY - {"virtual"})

    can_log = logging.getLogger("can")
    prev_level = can_log.level
    can_log.setLevel(logging.CRITICAL)
    # Several backends print missing-DLL messages to stderr during probe.
    sink = io.StringIO()
    try:
        with contextlib.redirect_stderr(sink), contextlib.redirect_stdout(sink):
            raw = list(
                can.detect_available_configs(interfaces=interfaces, timeout=timeout)
            )
    finally:
        can_log.setLevel(prev_level)

    if not any(c.get("interface") == "candle" for c in raw):
        try:
            from gs_usb.gs_usb import GsUsb

            for i, _dev in enumerate(GsUsb.scan()):
                raw.append({"interface": "gs_usb", "channel": i, "index": i})
        except Exception:
            pass

    channels: list[DetectedChannel] = []
    seen: set[str] = set()
    for cfg in _dedupe_real(raw):
        uid = _uid_real(cfg)
        if uid in seen:
            continue
        seen.add(uid)
        channels.append(
            DetectedChannel(
                uid=uid,
                label=_friendly_real_label(cfg),
                interface=str(cfg.get("interface", "")),
                bus_kwargs=_bus_kwargs_from_cfg(cfg),
                kind=EmulationMode.REAL,
            )
        )

    def rank(ch: DetectedChannel) -> tuple[int, str]:
        if ch.interface in ("candle", "gs_usb"):
            return (0, ch.label)
        if ch.interface == "vector":
            return (1, ch.label)
        return (2, ch.label)

    return sorted(channels, key=rank)


def detect_virtual_hardware() -> list[DetectedChannel]:
    """Stable python-can virtual channels (no USB / Vector drivers needed)."""
    channels: list[DetectedChannel] = []
    for name in VIRTUAL_CHANNELS:
        channels.append(
            DetectedChannel(
                uid=f"virtual:{name}",
                label=f"Virtual CAN  ({name})",
                interface="virtual",
                bus_kwargs={"interface": "virtual", "channel": name},
                kind=EmulationMode.VIRTUAL,
            )
        )
    return channels


def detect_hardware(
    mode: EmulationMode | str = EmulationMode.REAL,
    timeout: float = 6.0,
) -> list[DetectedChannel]:
    """Discover channels for the selected emulation mode."""
    if isinstance(mode, str):
        mode = EmulationMode(mode)
    if mode is EmulationMode.VIRTUAL:
        return detect_virtual_hardware()
    return detect_real_hardware(timeout=timeout)


def find_channel(
    mode: EmulationMode | str,
    channel: str,
    timeout: float = 6.0,
) -> DetectedChannel:
    """Resolve a user channel: list index (1, 2, …), uid, label, or short name."""
    channels = detect_hardware(mode=mode, timeout=timeout)
    needle = channel.strip()

    # Simple: --channel 1 means the first row from --list-channels
    if needle.isdigit():
        idx = int(needle)
        if 1 <= idx <= len(channels):
            return channels[idx - 1]
        raise ValueError(
            f"Channel number {idx} is out of range "
            f"(detected {len(channels)} channel(s) in mode {mode!r})"
        )

    for ch in channels:
        if ch.uid == needle or ch.label == needle:
            return ch
        raw_ch = ch.bus_kwargs.get("channel")
        if str(raw_ch) == needle or needle == f"{ch.interface}:{raw_ch}":
            return ch
        if ch.interface == "virtual" and needle in VIRTUAL_CHANNELS and raw_ch == needle:
            return ch
    available = ", ".join(f"{i}:{c.label}" for i, c in enumerate(channels, start=1)) or "(none)"
    raise ValueError(
        f"Channel {channel!r} not found in mode {mode!r}. "
        f"Use a number from the list ({available})"
    )


def open_bus(channel: DetectedChannel, bitrate: int = 500_000, **extra: Any) -> can.BusABC:
    """Open a Bus from a DetectedChannel."""
    kwargs = dict(channel.bus_kwargs)
    kwargs.update(extra)
    if channel.interface != "virtual":
        kwargs.setdefault("bitrate", bitrate)
    if kwargs.get("interface") == "vector":
        kwargs.setdefault("app_name", "python-can")
    if kwargs.get("interface") == "virtual":
        # TX-only sessions should not echo into their own RX queue.
        kwargs.setdefault("receive_own_messages", False)
    return can.Bus(**kwargs)


def supported_interface_names() -> list[str]:
    return sorted(VALID_INTERFACES)
