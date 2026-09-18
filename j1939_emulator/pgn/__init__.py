"""PGN / SPN state and encoders matching standalone_v1.0.html."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


STARTER_LABELS = {
    0: "Start Not Requested",
    2: "Starter Active (Gear Engaged)",
    3: "Start Finished",
    4: "Engine Cranking",
}


@dataclass
class SignalState:
    """Runtime SPN values for the five v1.0 PGNs."""

    # EEC1
    spn190_rpm: float = 1250.0
    spn513_torque_pct: float = 48.0
    spn512_demand_torque_pct: float = 50.0
    spn899_starter_mode: int = 3
    eec1_enabled: bool = True

    # CCVS
    spn84_speed_mph: float = 58.4
    spn595_cruise: bool = True
    spn597_brake: bool = False
    spn598_clutch: bool = False
    ccvs_enabled: bool = True

    # FUEL
    spn183_fuel_rate_gal_h: float = 7.8
    spn184_economy_mpg: float = 7.48
    spn91_throttle_pct: float = 42.0
    fuel_enabled: bool = True

    # ET1
    spn110_coolant_c: float = 89.0
    spn175_oil_c: float = 98.0
    spn174_fuel_c: float = 34.0
    et1_enabled: bool = True

    # VD
    spn917_total_mi: float = 248912.4
    spn918_trip_mi: float = 418.6
    vd_enabled: bool = True

    # Cycle times (ms) — configurable per PGN
    cycle_eec1_ms: int = 20
    cycle_ccvs_ms: int = 100
    cycle_fuel_ms: int = 100
    cycle_et1_ms: int = 1000
    cycle_vd_ms: int = 1000

    _listeners: list[Callable[[], None]] = field(default_factory=list, repr=False)

    def on_change(self, cb: Callable[[], None]) -> None:
        self._listeners.append(cb)

    def clear_listeners(self) -> None:
        self._listeners.clear()

    def notify(self) -> None:
        for cb in list(self._listeners):
            cb()

    def starter_label(self) -> str:
        return STARTER_LABELS.get(self.spn899_starter_mode, f"Mode {self.spn899_starter_mode}")

    def set_spn(self, key: str, value: object) -> None:
        """Set a known SPN field by dotted or flat key and notify listeners."""
        attr = self._spn_attr(key)
        cur = getattr(self, attr)
        if isinstance(cur, bool):
            if isinstance(value, bool):
                setattr(self, attr, value)
            elif isinstance(value, str):
                setattr(self, attr, value.strip().lower() in ("1", "true", "yes", "on", "active"))
            else:
                setattr(self, attr, bool(int(value)))  # type: ignore[arg-type]
        elif attr.startswith("cycle_") or attr == "spn899_starter_mode":
            code = int(float(value))  # type: ignore[arg-type]
            if attr == "spn899_starter_mode" and code not in STARTER_LABELS:
                raise ValueError(f"Invalid starter mode {code}; expected one of {sorted(STARTER_LABELS)}")
            if attr.startswith("cycle_") and code < 1:
                raise ValueError("Cycle time must be >= 1 ms")
            setattr(self, attr, code)
        else:
            setattr(self, attr, float(value))  # type: ignore[arg-type]
        self.notify()

    def get_spn(self, key: str) -> object:
        """Read a known SPN field by dotted or flat key."""
        return getattr(self, self._spn_attr(key))

    @staticmethod
    def _spn_attr(key: str) -> str:
        mapping = {
            "eec1.spn190_rpm": "spn190_rpm",
            "spn190_rpm": "spn190_rpm",
            "eec1.spn513_torque_pct": "spn513_torque_pct",
            "spn513_torque_pct": "spn513_torque_pct",
            "eec1.spn512_demand_torque_pct": "spn512_demand_torque_pct",
            "spn512_demand_torque_pct": "spn512_demand_torque_pct",
            "eec1.spn899_starter_mode": "spn899_starter_mode",
            "spn899_starter_mode": "spn899_starter_mode",
            "ccvs.spn84_speed_mph": "spn84_speed_mph",
            "spn84_speed_mph": "spn84_speed_mph",
            "ccvs.spn595_cruise": "spn595_cruise",
            "spn595_cruise": "spn595_cruise",
            "ccvs.spn597_brake": "spn597_brake",
            "spn597_brake": "spn597_brake",
            "ccvs.spn598_clutch": "spn598_clutch",
            "spn598_clutch": "spn598_clutch",
            "fuel.spn183_fuel_rate_gal_h": "spn183_fuel_rate_gal_h",
            "spn183_fuel_rate_gal_h": "spn183_fuel_rate_gal_h",
            "fuel.spn184_economy_mpg": "spn184_economy_mpg",
            "spn184_economy_mpg": "spn184_economy_mpg",
            "fuel.spn91_throttle_pct": "spn91_throttle_pct",
            "spn91_throttle_pct": "spn91_throttle_pct",
            "et1.spn110_coolant_c": "spn110_coolant_c",
            "spn110_coolant_c": "spn110_coolant_c",
            "et1.spn175_oil_c": "spn175_oil_c",
            "spn175_oil_c": "spn175_oil_c",
            "et1.spn174_fuel_c": "spn174_fuel_c",
            "spn174_fuel_c": "spn174_fuel_c",
            "vd.spn917_total_mi": "spn917_total_mi",
            "spn917_total_mi": "spn917_total_mi",
            "vd.spn918_trip_mi": "spn918_trip_mi",
            "spn918_trip_mi": "spn918_trip_mi",
            "eec1.cycle_ms": "cycle_eec1_ms",
            "cycle_eec1_ms": "cycle_eec1_ms",
            "ccvs.cycle_ms": "cycle_ccvs_ms",
            "cycle_ccvs_ms": "cycle_ccvs_ms",
            "fuel.cycle_ms": "cycle_fuel_ms",
            "cycle_fuel_ms": "cycle_fuel_ms",
            "et1.cycle_ms": "cycle_et1_ms",
            "cycle_et1_ms": "cycle_et1_ms",
            "vd.cycle_ms": "cycle_vd_ms",
            "cycle_vd_ms": "cycle_vd_ms",
        }
        attr = mapping.get(key)
        if attr is None:
            raise KeyError(f"Unknown SPN key: {key}")
        return attr


# CAN IDs (priority + PGN + SA 0x00) matching HTML mock
CAN_ID_EEC1 = 0x0CF00400
CAN_ID_CCVS = 0x18FEF100
CAN_ID_FUEL = 0x18FEF200
CAN_ID_ET1 = 0x18FEEE00
CAN_ID_VD = 0x18FEE000

PERIOD_EEC1_S = 0.020
PERIOD_CCVS_S = 0.100
PERIOD_FUEL_S = 0.100
PERIOD_ET1_S = 1.000
PERIOD_VD_S = 1.000


def encode_eec1(state: SignalState) -> bytes:
    """Match HTML recalcEec1()."""
    raw_rpm = min(65535, max(0, round(state.spn190_rpm / 0.125)))
    raw_torque = min(250, max(0, round(state.spn513_torque_pct + 125)))
    raw_demand = min(250, max(0, round(state.spn512_demand_torque_pct + 125)))
    byte6 = 0xF0 | (int(state.spn899_starter_mode) & 0x0F)
    return bytes(
        [
            0xF0,
            raw_demand,
            raw_torque,
            raw_rpm & 0xFF,
            (raw_rpm >> 8) & 0xFF,
            byte6,
            0xFF,
            0xFF,
        ]
    )


def encode_ccvs(state: SignalState) -> bytes:
    """Match HTML recalcCcvs()."""
    kmh = state.spn84_speed_mph * 1.60934
    raw_speed = min(65535, max(0, round(kmh * 256)))
    b4 = 0x00
    if state.spn597_brake:
        b4 |= 0x10
    if state.spn598_clutch:
        b4 |= 0x40
    b5 = 0x01 if state.spn595_cruise else 0x00
    return bytes(
        [
            0xA1,
            raw_speed & 0xFF,
            (raw_speed >> 8) & 0xFF,
            b4,
            b5,
            0x00,
            0xFF,
            0xFF,
        ]
    )


def encode_fuel(state: SignalState) -> bytes:
    """LFE PGN 65266 — SPN 183 fuel rate, SPN 184 economy, SPN 91 throttle.

    SPN 184 Instantaneous Fuel Economy: 1/512 km/kg per bit (SAE).
    UI unit is mpg; convert mpg → km/L → km/kg (diesel density 0.85 kg/L).
    """
    fuel_lh = state.spn183_fuel_rate_gal_h * 3.78541
    raw_fuel = min(65535, max(0, round(fuel_lh / 0.05)))
    km_per_l = state.spn184_economy_mpg * 1.60934 / 3.78541
    km_per_kg = km_per_l / 0.85
    raw_econ = min(65535, max(0, round(km_per_kg * 512)))
    raw_pedal = min(250, max(0, round(state.spn91_throttle_pct / 0.4)))
    return bytes(
        [
            raw_fuel & 0xFF,
            (raw_fuel >> 8) & 0xFF,
            raw_econ & 0xFF,
            (raw_econ >> 8) & 0xFF,
            0xFF,  # SPN 185 average economy — not available
            0xFF,
            raw_pedal,
            0xFF,
        ]
    )


def encode_et1(state: SignalState) -> bytes:
    """Match HTML recalcEt1() — coolant, fuel temp, oil temp order."""
    raw_c = min(250, max(0, round(state.spn110_coolant_c + 40)))
    raw_f = min(250, max(0, round(state.spn174_fuel_c + 40)))
    raw_o = min(250, max(0, round(state.spn175_oil_c + 40)))
    return bytes([raw_c, raw_f, raw_o, 0x98, 0xFF, 0xFF, 0xFF, 0xFF])


def encode_vd(state: SignalState) -> bytes:
    """Match HTML recalcVd() — mi→km / 0.125 km resolution."""
    dist_km = state.spn917_total_mi * 1.60934
    raw_dist = round(dist_km / 0.125)
    trip_km = state.spn918_trip_mi * 1.60934
    raw_trip = round(trip_km / 0.125)
    return bytes(
        [
            raw_dist & 0xFF,
            (raw_dist >> 8) & 0xFF,
            (raw_dist >> 16) & 0xFF,
            (raw_dist >> 24) & 0xFF,
            raw_trip & 0xFF,
            (raw_trip >> 8) & 0xFF,
            0x00,
            0x00,
        ]
    )


def payload_hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def all_payloads(state: SignalState) -> dict[str, str]:
    return {
        "eec1": payload_hex(encode_eec1(state)),
        "ccvs": payload_hex(encode_ccvs(state)),
        "fuel": payload_hex(encode_fuel(state)),
        "et1": payload_hex(encode_et1(state)),
        "vd": payload_hex(encode_vd(state)),
    }
