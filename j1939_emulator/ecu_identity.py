"""ECU identity: SA 0x00, J1939-81 NAME, VIN (PGN 65260)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

# Milestone / HTML defaults
DEFAULT_VIN = "1HTMMAAL7GH123456"
DEFAULT_SOURCE_ADDRESS = 0x00
DEFAULT_NAME = 0x0020000000000000
DEFAULT_INDUSTRY_GROUP = 0
DEFAULT_VEHICLE_SYSTEM = 0

# PGN 65260 Vehicle Identification (VI) — PDU format/specific for send_pgn
PGN_VI = 65260  # 0xFEEC
VI_PDU_FORMAT = 0xFE
VI_PDU_SPECIFIC = 0xEC
VI_PRIORITY = 6

# Address claimed (broadcast) — observed on bus as 0x18EEFF00 for SA 0x00
CAN_ID_ADDRESS_CLAIMED = 0x18EEFF00

_VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{1,17}$")


def validate_vin(vin: str, *, allow_empty: bool = False) -> str:
    """Normalize and validate VIN. Returns uppercase VIN."""
    if vin is None:
        raise ValueError("VIN is required")
    cleaned = str(vin).strip().upper()
    if not cleaned:
        if allow_empty:
            return ""
        raise ValueError("VIN cannot be empty")
    if len(cleaned) > 17:
        raise ValueError("VIN must be at most 17 characters")
    if not _VIN_RE.match(cleaned):
        raise ValueError(
            "VIN may only contain A–Z and 0–9 (excluding I, O, Q)"
        )
    return cleaned


def name_bytes_le(name: int = DEFAULT_NAME) -> bytes:
    """Little-endian 8-byte NAME as transmitted in Address Claimed."""
    return int(name).to_bytes(8, byteorder="little", signed=False)


@dataclass
class EcuIdentity:
    """Single v1.0 ECU node identity."""

    vin: str = DEFAULT_VIN
    source_address: int = DEFAULT_SOURCE_ADDRESS
    name: int = DEFAULT_NAME
    industry_group: int = DEFAULT_INDUSTRY_GROUP
    vehicle_system: int = DEFAULT_VEHICLE_SYSTEM
    _listeners: list[Callable[[], None]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self.vin = validate_vin(self.vin)

    def on_change(self, cb: Callable[[], None]) -> None:
        self._listeners.append(cb)

    def clear_listeners(self) -> None:
        self._listeners.clear()

    def notify(self) -> None:
        for cb in list(self._listeners):
            cb()

    def set_vin(self, vin: str) -> str:
        self.vin = validate_vin(vin)
        self.notify()
        return self.vin

    @property
    def name_hex(self) -> str:
        return f"0x{self.name:016X}"

    def vin_payload(self) -> list[int]:
        """ASCII VIN bytes for PGN 65260 (may exceed 8 → BAM/TP)."""
        return list(self.vin.encode("ascii"))
