"""Diagnostics: configurable DTCs with DM1 / DM2 / DM3 (J1939-73)."""

from __future__ import annotations

from enum import Enum
from typing import Callable, Iterable, Literal

from j1939.diagnostic_messages import DTC, DtcLamp

# PGN constants (J1939-73 / can-j1939 ParameterGroupNumber.PGN)
PGN_DM1 = 65226  # 0xFECA — Active DTCs
PGN_DM2 = 65227  # 0xFECB — Previously active DTCs
PGN_DM3 = 65228  # 0xFECC — Clear/reset previously active
PGN_ACKNOWLEDGEMENT = 59392  # 0xE800 — J1939-21 ACK/NACK
PGN_REQUEST = 59904  # 0xEA00

CAN_ID_DM1 = 0x18FECA00  # Prio 6, SA 0x00 (single-frame)
DM1_CYCLE_MS = 1000

# Fixed v1.0 demo presets (still the default catalogue)
DTC1_SPN, DTC1_FMI = 110, 3  # Coolant temp voltage high → Amber Warning
DTC2_SPN, DTC2_FMI = 190, 0  # Crankshaft overspeed → Red Stop

LampKey = Literal["pl", "awl", "rsl", "mil"]
_VALID_LAMPS: frozenset[str] = frozenset({"pl", "awl", "rsl", "mil"})

# Empty-list pad per J1939-73 §5.7.1 Example 2 / §5.7.2 Example 2
_NA_SPN = 524_287
_NA_FMI = 31
_NA_OC = 127


class DtcStatus(str, Enum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    PREVIOUSLY_ACTIVE = "previously_active"


class DtcEntry:
    """One configurable diagnostic trouble code."""

    __slots__ = ("id", "spn", "fmi", "oc", "lamp", "label", "status")

    def __init__(
        self,
        id: str,
        spn: int,
        fmi: int,
        oc: int = 0,
        lamp: LampKey = "awl",
        label: str = "",
        status: DtcStatus = DtcStatus.INACTIVE,
    ) -> None:
        self.id = id
        self.spn = int(spn)
        self.fmi = int(fmi) & 0x1F
        self.oc = max(0, min(126, int(oc)))
        self.lamp = lamp
        self.label = label
        self.status = status

    def as_wire_dict(self) -> dict[str, int]:
        return {"spn": self.spn, "fmi": self.fmi, "oc": self.oc & 0x7F}


def _default_catalogue() -> list[DtcEntry]:
    return [
        DtcEntry(
            id="coolant_volt_high",
            spn=DTC1_SPN,
            fmi=DTC1_FMI,
            oc=0,
            lamp="awl",
            label="Engine Coolant Temp Voltage High",
        ),
        DtcEntry(
            id="crank_overspeed",
            spn=DTC2_SPN,
            fmi=DTC2_FMI,
            oc=0,
            lamp="rsl",
            label="Engine Crankshaft Overspeed",
        ),
    ]


def normalize_lamp(raw: str | None) -> LampKey:
    key = (raw or "awl").strip().lower()
    if key not in _VALID_LAMPS:
        raise ValueError(f"Invalid lamp {raw!r}; expected one of {sorted(_VALID_LAMPS)}")
    return key  # type: ignore[return-value]


class DiagnosticState:
    """Active + previously active DTC memory for DM1/DM2/DM3."""

    def __init__(
        self,
        *,
        dtcs: list[DtcEntry] | None = None,
        dm1_cycle_ms: int = DM1_CYCLE_MS,
        dtc_spn110_fmi3: bool = False,
        dtc_spn190_fmi0: bool = False,
    ) -> None:
        self.dtcs: list[DtcEntry] = list(dtcs) if dtcs is not None else _default_catalogue()
        self.dm1_cycle_ms = max(100, int(dm1_cycle_ms))
        self._listeners: list[Callable[[], None]] = []
        # Apply legacy bools after catalogue exists (without double-notify spam)
        if dtc_spn110_fmi3:
            e = self._ensure_demo(
                DTC1_SPN,
                DTC1_FMI,
                lamp="awl",
                label="Engine Coolant Temp Voltage High",
                id_="coolant_volt_high",
            )
            e.status = DtcStatus.ACTIVE
        if dtc_spn190_fmi0:
            e = self._ensure_demo(
                DTC2_SPN,
                DTC2_FMI,
                lamp="rsl",
                label="Engine Crankshaft Overspeed",
                id_="crank_overspeed",
            )
            e.status = DtcStatus.ACTIVE

    # --- back-compat for v1.0 two-bool API ---------------------------------

    @property
    def dtc_spn110_fmi3(self) -> bool:
        e = self._find_demo(DTC1_SPN, DTC1_FMI)
        return e is not None and e.status == DtcStatus.ACTIVE

    @dtc_spn110_fmi3.setter
    def dtc_spn110_fmi3(self, active: bool) -> None:
        self.set_dtc1(bool(active))

    @property
    def dtc_spn190_fmi0(self) -> bool:
        e = self._find_demo(DTC2_SPN, DTC2_FMI)
        return e is not None and e.status == DtcStatus.ACTIVE

    @dtc_spn190_fmi0.setter
    def dtc_spn190_fmi0(self, active: bool) -> None:
        self.set_dtc2(bool(active))

    # --- listeners ---------------------------------------------------------

    def on_change(self, cb: Callable[[], None]) -> None:
        self._listeners.append(cb)

    def clear_listeners(self) -> None:
        self._listeners.clear()

    def notify(self) -> None:
        for cb in list(self._listeners):
            cb()

    # --- queries -----------------------------------------------------------

    @property
    def active_count(self) -> int:
        return sum(1 for e in self.dtcs if e.status == DtcStatus.ACTIVE)

    @property
    def previously_active_count(self) -> int:
        return sum(
            1
            for e in self.dtcs
            if e.status == DtcStatus.PREVIOUSLY_ACTIVE and e.oc != 0
        )

    @property
    def dm1_broadcasting(self) -> bool:
        return self.active_count > 0

    def active_entries(self) -> list[DtcEntry]:
        return [e for e in self.dtcs if e.status == DtcStatus.ACTIVE]

    def previously_active_entries(self) -> list[DtcEntry]:
        """DM2 list: previously active with OC ≠ 0 (J1939-73 §5.7.2)."""
        return [
            e
            for e in self.dtcs
            if e.status == DtcStatus.PREVIOUSLY_ACTIVE and e.oc != 0
        ]

    def list_dtcs(self) -> list[DtcEntry]:
        return list(self.dtcs)

    def find(self, key: str | int) -> DtcEntry | None:
        """Resolve by id, demo slot (1|2), or SPN."""
        s = str(key).strip().lower()
        if s in ("1", "dtc1"):
            return self._find_demo(DTC1_SPN, DTC1_FMI)
        if s in ("2", "dtc2"):
            return self._find_demo(DTC2_SPN, DTC2_FMI)
        for e in self.dtcs:
            if e.id.lower() == s:
                return e
        try:
            spn = int(s, 0)
        except ValueError:
            return None
        matches = [e for e in self.dtcs if e.spn == spn]
        if not matches:
            return None
        for status in (DtcStatus.ACTIVE, DtcStatus.PREVIOUSLY_ACTIVE, DtcStatus.INACTIVE):
            for e in matches:
                if e.status == status:
                    return e
        return matches[0]

    def _find_demo(self, spn: int, fmi: int) -> DtcEntry | None:
        for e in self.dtcs:
            if e.spn == spn and e.fmi == fmi:
                return e
        return None

    def _ensure_demo(
        self, spn: int, fmi: int, *, lamp: LampKey, label: str, id_: str
    ) -> DtcEntry:
        e = self._find_demo(spn, fmi)
        if e is not None:
            return e
        e = DtcEntry(id=id_, spn=spn, fmi=fmi, oc=0, lamp=lamp, label=label)
        self.dtcs.append(e)
        return e

    # --- mutations ---------------------------------------------------------

    def add_dtc(
        self,
        spn: int,
        fmi: int,
        oc: int = 0,
        *,
        lamp: str = "awl",
        label: str = "",
        id: str | None = None,
        active: bool = False,
    ) -> DtcEntry:
        spn_i = int(spn)
        fmi_i = int(fmi) & 0x1F
        if not (0 <= spn_i <= 524_287):
            raise ValueError(f"SPN out of range: {spn_i}")
        lamp_k = normalize_lamp(lamp)
        entry_id = id or f"spn{spn_i}_fmi{fmi_i}"
        if any(e.id == entry_id for e in self.dtcs):
            raise ValueError(f"DTC id already exists: {entry_id}")
        existing = self._find_demo(spn_i, fmi_i)
        if existing is not None:
            raise ValueError(
                f"DTC SPN {spn_i}/FMI {fmi_i} already configured as {existing.id}"
            )
        entry = DtcEntry(
            id=entry_id,
            spn=spn_i,
            fmi=fmi_i,
            oc=oc,
            lamp=lamp_k,
            label=label or f"SPN {spn_i} / FMI {fmi_i}",
            status=DtcStatus.ACTIVE if active else DtcStatus.INACTIVE,
        )
        self.dtcs.append(entry)
        self.notify()
        return entry

    def set_active(self, key: str | int, active: bool) -> DtcEntry:
        entry = self.find(key)
        if entry is None:
            raise KeyError(f"Unknown DTC: {key}")
        if active:
            self._activate(entry)
        else:
            self._deactivate(entry)
        self.notify()
        return entry

    def _activate(self, entry: DtcEntry) -> None:
        entry.status = DtcStatus.ACTIVE

    def _deactivate(self, entry: DtcEntry) -> None:
        """Heal active → previously active; bump OC (J1939-73 §5.7.1.7)."""
        if entry.status != DtcStatus.ACTIVE:
            return
        entry.oc = min(126, entry.oc + 1)
        entry.status = DtcStatus.PREVIOUSLY_ACTIVE

    def set_dtc1(self, active: bool) -> None:
        e = self._ensure_demo(
            DTC1_SPN,
            DTC1_FMI,
            lamp="awl",
            label="Engine Coolant Temp Voltage High",
            id_="coolant_volt_high",
        )
        if active:
            self._activate(e)
        elif e.status == DtcStatus.ACTIVE:
            self._deactivate(e)
        self.notify()

    def set_dtc2(self, active: bool) -> None:
        e = self._ensure_demo(
            DTC2_SPN,
            DTC2_FMI,
            lamp="rsl",
            label="Engine Crankshaft Overspeed",
            id_="crank_overspeed",
        )
        if active:
            self._activate(e)
        elif e.status == DtcStatus.ACTIVE:
            self._deactivate(e)
        self.notify()

    def set_both(self, active: bool) -> None:
        if active:
            self.inject_demo()
        else:
            self.clear_active()

    def inject_demo(self) -> None:
        """Enable the two v1.0 preset faults (active)."""
        for setter in (self.set_dtc1, self.set_dtc2):
            setter(True)

    def inject_both(self) -> None:
        self.inject_demo()

    def clear_active(self) -> None:
        """Move all active DTCs to previously active (heal)."""
        changed = False
        for e in list(self.dtcs):
            if e.status == DtcStatus.ACTIVE:
                self._deactivate(e)
                changed = True
        if changed:
            self.notify()

    def clear_previously_active(self) -> None:
        """DM3: erase previously active diagnostic information."""
        changed = False
        for e in self.dtcs:
            if e.status == DtcStatus.PREVIOUSLY_ACTIVE:
                e.status = DtcStatus.INACTIVE
                e.oc = 0
                changed = True
        if changed:
            self.notify()

    def clear_all(self) -> None:
        """Heal actives then erase previously active (full wipe)."""
        for e in list(self.dtcs):
            if e.status == DtcStatus.ACTIVE:
                self._deactivate(e)
        for e in self.dtcs:
            if e.status == DtcStatus.PREVIOUSLY_ACTIVE:
                e.status = DtcStatus.INACTIVE
                e.oc = 0
        self.notify()

    # --- lamp / payload helpers --------------------------------------------

    def lamp_status(self) -> dict[str, int]:
        """Lamp dict from the **active** set (present state for DM1 and DM2)."""
        lamps = {
            "pl": DtcLamp.OFF,
            "awl": DtcLamp.OFF,
            "rsl": DtcLamp.OFF,
            "mil": DtcLamp.OFF,
        }
        for e in self.active_entries():
            lamps[e.lamp] = DtcLamp.ON
        return lamps

    def dtc_list(self) -> list[dict[str, int]]:
        """Active DTCs for DM1 / Dm1.start_send callback."""
        return [e.as_wire_dict() for e in self.active_entries()]

    def previously_active_dtc_list(self) -> list[dict[str, int]]:
        return [e.as_wire_dict() for e in self.previously_active_entries()]

    def dm1_callback(self):
        """Callback signature for j1939.Dm1.start_send."""
        return self.lamp_status(), self.dtc_list()

    def dm2_callback(self):
        """Lamps (present/active state) + previously active DTC list."""
        return self.lamp_status(), self.previously_active_dtc_list()


def encode_diagnostic_message(
    lamp_status: dict[str, int],
    dtc_dicts: Iterable[dict[str, int]],
    *,
    empty_as_na: bool = False,
) -> bytes:
    """Encode DM1/DM2 payload (same layout per J1939-73 §5.7.1 / §5.7.2).

    - 0 DTCs + empty_as_na: 8-byte NA pad (request / transition response)
    - 1 DTC: lamps + DTC + 0xFF pad to 8 bytes
    - 2+ DTCs: lamps + N×4 (may exceed 8 → BAM via send_pgn)
    """
    data = bytearray(DtcLamp().get_data(dict(lamp_status)))
    items = list(dtc_dicts)
    if not items:
        if empty_as_na:
            word = DTC(spn=_NA_SPN, fmi=_NA_FMI, oc=_NA_OC).dtc
            data.append(word & 0xFF)
            data.append((word >> 8) & 0xFF)
            data.append((word >> 16) & 0xFF)
            data.append((word >> 24) & 0xFF)
            data.extend([0xFF, 0xFF])
        return bytes(data)

    for dtc_dic in items:
        word = DTC(
            spn=int(dtc_dic["spn"]),
            fmi=int(dtc_dic["fmi"]),
            oc=int(dtc_dic.get("oc", 0)),
        ).dtc
        data.append(word & 0xFF)
        data.append((word >> 8) & 0xFF)
        data.append((word >> 16) & 0xFF)
        data.append((word >> 24) & 0xFF)
    if len(items) == 1:
        data.extend([0xFF, 0xFF])
    return bytes(data)


def encode_dm1(state: DiagnosticState, *, empty_as_na: bool | None = None) -> bytes:
    """Encode DM1 payload from DiagnosticState."""
    use_na = state.active_count == 0 if empty_as_na is None else empty_as_na
    return encode_diagnostic_message(
        state.lamp_status(),
        state.dtc_list(),
        empty_as_na=use_na,
    )


def encode_dm2(state: DiagnosticState) -> bytes:
    """Encode DM2 payload (lamps + previously active). Always NA-pad when empty."""
    return encode_diagnostic_message(
        state.lamp_status(),
        state.previously_active_dtc_list(),
        empty_as_na=True,
    )


def dtc_spn_fmi_from_payload(payload: bytes) -> list[tuple[int, int]]:
    """Parse SPN/FMI pairs from a DM1/DM2 payload (after 2 lamp bytes)."""
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
        # Skip NA empty-list placeholder (SPN 524287 / FMI 31)
        if dtc.spn == _NA_SPN and dtc.fmi == _NA_FMI:
            break
        out.append((dtc.spn, dtc.fmi))
        i += 4
    return out
