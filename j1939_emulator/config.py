"""TOML configuration for bus + PGN + ECU/VIN + diagnostics defaults."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib

from j1939_emulator.bus.detect import EmulationMode
from j1939_emulator.diagnostics import DiagnosticState
from j1939_emulator.ecu_identity import (
    DEFAULT_NAME,
    DEFAULT_SOURCE_ADDRESS,
    DEFAULT_VIN,
    EcuIdentity,
    validate_vin,
)
from j1939_emulator.pgn import SignalState


@dataclass
class BusConfig:
    mode: EmulationMode = EmulationMode.VIRTUAL
    channel: str = "vcan0"
    bitrate: int = 500_000


@dataclass
class AppConfig:
    bus: BusConfig
    signals: SignalState
    identity: EcuIdentity
    diagnostics: DiagnosticState
    vin: str = DEFAULT_VIN  # alias of identity.vin for back-compat
    start_on_launch: bool = True


_REQUIRED_SECTIONS = ("bus",)


def load_config(path: str | Path) -> AppConfig:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Config not found: {p}")
    with p.open("rb") as f:
        raw = tomllib.load(f)

    missing = [s for s in _REQUIRED_SECTIONS if s not in raw]
    if missing:
        raise ValueError(f"Missing required TOML section(s): {', '.join(missing)}")

    bus_raw = raw["bus"]
    for key in ("mode", "channel", "bitrate"):
        if key not in bus_raw:
            raise ValueError(f"Missing required [bus] key: {key}")

    mode_s = str(bus_raw["mode"]).strip().lower()
    if mode_s not in ("real", "virtual"):
        raise ValueError(f"Invalid bus.mode {mode_s!r}; expected 'real' or 'virtual'")
    bitrate = int(bus_raw["bitrate"])
    if bitrate not in (125_000, 250_000, 500_000, 1_000_000):
        raise ValueError(
            f"Invalid bitrate {bitrate}; expected 125000, 250000, 500000, or 1000000"
        )

    bus = BusConfig(
        mode=EmulationMode(mode_s),
        channel=str(bus_raw["channel"]),
        bitrate=bitrate,
    )

    signals = SignalState()
    _apply_pgn(signals, raw.get("pgn", {}).get("eec1"), "eec1")
    _apply_pgn(signals, raw.get("pgn", {}).get("ccvs"), "ccvs")
    _apply_pgn(signals, raw.get("pgn", {}).get("fuel"), "fuel")
    _apply_pgn(signals, raw.get("pgn", {}).get("et1"), "et1")
    _apply_pgn(signals, raw.get("pgn", {}).get("vd"), "vd")

    identity = _load_identity(raw)
    diagnostics = _load_diagnostics(raw)

    start_on_launch = bool(raw.get("bus", {}).get("start_on_launch", True))
    if "start_on_launch" in raw.get("run", {}):
        start_on_launch = bool(raw["run"]["start_on_launch"])

    return AppConfig(
        bus=bus,
        signals=signals,
        identity=identity,
        diagnostics=diagnostics,
        vin=identity.vin,
        start_on_launch=start_on_launch,
    )


def _load_identity(raw: dict) -> EcuIdentity:
    ecu = raw.get("ecu", {}) or {}
    vehicle = raw.get("vehicle", {}) or {}

    vin_raw = vehicle.get("vin", ecu.get("vin", DEFAULT_VIN))
    vin = validate_vin(str(vin_raw))

    sa = ecu.get("source_address", DEFAULT_SOURCE_ADDRESS)
    if isinstance(sa, str):
        sa = int(sa, 0)
    else:
        sa = int(sa)

    name = ecu.get("name", DEFAULT_NAME)
    if isinstance(name, str):
        name = int(name, 0)
    else:
        name = int(name)

    industry = int(ecu.get("industry_group", 0))
    vehicle_system = int(ecu.get("vehicle_system", vehicle.get("vehicle_system", 0)))

    return EcuIdentity(
        vin=vin,
        source_address=sa & 0xFF,
        name=name,
        industry_group=industry,
        vehicle_system=vehicle_system,
    )


def _load_diagnostics(raw: dict) -> DiagnosticState:
    diag = raw.get("diagnostics", {}) or {}
    return DiagnosticState(
        dtc_spn110_fmi3=bool(
            diag.get(
                "dtc_spn110_fmi3",
                diag.get("inject_coolant_voltage_high", False),
            )
        ),
        dtc_spn190_fmi0=bool(
            diag.get(
                "dtc_spn190_fmi0",
                diag.get("inject_crankshaft_overspeed", False),
            )
        ),
    )


def _apply_pgn(signals: SignalState, section: dict | None, name: str) -> None:
    if not section:
        return
    enabled = bool(section.get("enabled", True))
    if name == "eec1":
        signals.eec1_enabled = enabled
        if "spn190_rpm" in section:
            signals.spn190_rpm = float(section["spn190_rpm"])
        if "spn513_torque_pct" in section:
            signals.spn513_torque_pct = float(section["spn513_torque_pct"])
        if "spn512_demand_torque_pct" in section:
            signals.spn512_demand_torque_pct = float(section["spn512_demand_torque_pct"])
        if "spn899_starter_mode" in section:
            signals.spn899_starter_mode = int(section["spn899_starter_mode"])
        if "cycle_ms" in section:
            signals.cycle_eec1_ms = int(section["cycle_ms"])
    elif name == "ccvs":
        signals.ccvs_enabled = enabled
        if "spn84_speed_mph" in section:
            signals.spn84_speed_mph = float(section["spn84_speed_mph"])
        if "spn595_cruise" in section:
            signals.spn595_cruise = bool(section["spn595_cruise"])
        if "spn597_brake" in section:
            signals.spn597_brake = bool(section["spn597_brake"])
        if "spn598_clutch" in section:
            signals.spn598_clutch = bool(section["spn598_clutch"])
        if "cycle_ms" in section:
            signals.cycle_ccvs_ms = int(section["cycle_ms"])
    elif name == "fuel":
        signals.fuel_enabled = enabled
        if "spn183_fuel_rate_gal_h" in section:
            signals.spn183_fuel_rate_gal_h = float(section["spn183_fuel_rate_gal_h"])
        if "spn184_economy_mpg" in section:
            signals.spn184_economy_mpg = float(section["spn184_economy_mpg"])
        if "spn91_throttle_pct" in section:
            signals.spn91_throttle_pct = float(section["spn91_throttle_pct"])
        if "cycle_ms" in section:
            signals.cycle_fuel_ms = int(section["cycle_ms"])
    elif name == "et1":
        signals.et1_enabled = enabled
        if "spn110_coolant_c" in section:
            signals.spn110_coolant_c = float(section["spn110_coolant_c"])
        if "spn175_oil_c" in section:
            signals.spn175_oil_c = float(section["spn175_oil_c"])
        if "spn174_fuel_c" in section:
            signals.spn174_fuel_c = float(section["spn174_fuel_c"])
        if "cycle_ms" in section:
            signals.cycle_et1_ms = int(section["cycle_ms"])
    elif name == "vd":
        signals.vd_enabled = enabled
        if "spn917_total_mi" in section:
            signals.spn917_total_mi = float(section["spn917_total_mi"])
        if "spn918_trip_mi" in section:
            signals.spn918_trip_mi = float(section["spn918_trip_mi"])
        if "cycle_ms" in section:
            signals.cycle_vd_ms = int(section["cycle_ms"])
