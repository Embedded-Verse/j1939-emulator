"""Diagnostics: two injectable DTCs and DM1 (PGN 65226) encoding."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from j1939.diagnostic_messages import DTC, DtcLamp

# PGN 65226 DM1 — CAN ID 0x18FECA00 (Prio 6, SA 0x00)
PGN_DM1 = 65226  # 0xFECA
CAN_ID_DM1 = 0x18FECA00
DM1_CYCLE_MS = 1000

# Fixed v1.0 fault set
DTC1_SPN, DTC1_FMI = 110, 3  # Coolant temp voltage high → Amber Warning
DTC2_SPN, DTC2_FMI = 190, 0  # Crankshaft overspeed → Red Stop


@dataclass
class DiagnosticState:
    """Exactly two injectable DTCs for v1.0."""

    dtc_spn110_fmi3: bool = False
    dtc_spn190_fmi0: bool = False
    _listeners: list[Callable[[], None]] = field(default_factory=list, repr=False)

    def on_change(self, cb: Callable[[], None]) -> None:
        self._listeners.append(cb)

    def clear_listeners(self) -> None:
        self._listeners.clear()

    def notify(self) -> None:
        for cb in list(self._listeners):
            cb()

    @property
    def active_count(self) -> int:
        return int(self.dtc_spn110_fmi3) + int(self.dtc_spn190_fmi0)

    def set_dtc1(self, active: bool) -> None:
        self.dtc_spn110_fmi3 = bool(active)
        self.notify()

    def set_dtc2(self, active: bool) -> None:
        self.dtc_spn190_fmi0 = bool(active)
        self.notify()

    def set_both(self, active: bool) -> None:
        self.dtc_spn110_fmi3 = bool(active)
        self.dtc_spn190_fmi0 = bool(active)
        self.notify()

    def clear_all(self) -> None:
        self.set_both(False)

    def inject_both(self) -> None:
        self.set_both(True)

    def lamp_status(self) -> dict[str, int]:
        """Lamp dict for can-j1939 Dm1 / DtcLamp.get_data."""
        return {
            "pl": DtcLamp.OFF,
            "awl": DtcLamp.ON if self.dtc_spn110_fmi3 else DtcLamp.OFF,
            "rsl": DtcLamp.ON if self.dtc_spn190_fmi0 else DtcLamp.OFF,
            "mil": DtcLamp.OFF,
        }

    def dtc_list(self) -> list[dict[str, int]]:
        out: list[dict[str, int]] = []
        if self.dtc_spn110_fmi3:
            out.append({"spn": DTC1_SPN, "fmi": DTC1_FMI, "oc": 1})
        if self.dtc_spn190_fmi0:
            out.append({"spn": DTC2_SPN, "fmi": DTC2_FMI, "oc": 1})
        return out

    def dm1_callback(self):
        """Callback signature for j1939.Dm1.start_send."""
        return self.lamp_status(), self.dtc_list()


def encode_dm1(state: DiagnosticState) -> bytes:
    """Encode DM1 payload (lamp + DTCs). May exceed 8 bytes when both active."""
    data = bytearray(DtcLamp().get_data(state.lamp_status()))
    for dtc_dic in state.dtc_list():
        word = DTC(spn=dtc_dic["spn"], fmi=dtc_dic["fmi"], oc=dtc_dic["oc"]).dtc
        data.append(word & 0xFF)
        data.append((word >> 8) & 0xFF)
        data.append((word >> 16) & 0xFF)
        data.append((word >> 24) & 0xFF)
    # Single-frame pad unused DTC slot with 0xFF when exactly one DTC (J1939-73)
    if len(state.dtc_list()) == 1:
        data.extend([0xFF, 0xFF])
    return bytes(data)


def dtc_spn_fmi_from_payload(payload: bytes) -> list[tuple[int, int]]:
    """Parse SPN/FMI pairs from a single-frame DM1 payload (after 2 lamp bytes)."""
    out: list[tuple[int, int]] = []
    i = 2
    while i + 3 < len(payload):
        chunk = payload[i : i + 4]
        if chunk == b"\xff\xff\xff\xff" or chunk[:2] == b"\xff\xff":
            break
        word = int.from_bytes(chunk, "little")
        dtc = DTC(dtc=word)
        if dtc.spn == 0 and dtc.fmi == 0:
            break
        out.append((dtc.spn, dtc.fmi))
        i += 4
    return out
