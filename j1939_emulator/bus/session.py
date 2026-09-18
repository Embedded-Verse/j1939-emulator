"""Bus session: START / STOP / RESET, cyclic PGN TX, J1939 claim/VIN/DM1, live stats."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import can
from j1939 import ControllerApplication, ElectronicControlUnit, Name
from j1939.diagnostic_messages import Dm1

# can-j1939 job-thread cleanup typos CoUnitialize on Windows; map to real API.
try:
    import pythoncom as _pythoncom

    if not hasattr(_pythoncom, "CoUnitialize"):
        _pythoncom.CoUnitialize = getattr(
            _pythoncom, "CoUninitialize", lambda: None
        )
except Exception:
    pass

from j1939_emulator.bus.detect import DetectedChannel, EmulationMode
from j1939_emulator.diagnostics import DM1_CYCLE_MS, DiagnosticState
from j1939_emulator.ecu_identity import (
    VI_PDU_FORMAT,
    VI_PDU_SPECIFIC,
    VI_PRIORITY,
    EcuIdentity,
)
from j1939_emulator.pgn import (
    CAN_ID_CCVS,
    CAN_ID_EEC1,
    CAN_ID_ET1,
    CAN_ID_FUEL,
    CAN_ID_VD,
    SignalState,
    encode_ccvs,
    encode_eec1,
    encode_et1,
    encode_fuel,
    encode_vd,
)

_BITS_PER_FRAME = 142


@dataclass
class SessionStats:
    running: bool = False
    uptime_s: float = 0.0
    tx_count: int = 0
    load_pct: float = 0.0
    bitrate: int = 500_000
    mode: EmulationMode = EmulationMode.VIRTUAL
    channel_label: str = ""
    sa: int = 0x00
    active_dtcs: int = 0
    address_claimed: bool = False


class _PeriodicSender(threading.Thread):
    """Daemon thread that sends one arbitration ID; period read live each cycle."""

    def __init__(
        self,
        bus: can.BusABC,
        arb_id: int,
        period_fn: Callable[[], float],
        data_fn: Callable[[], bytes],
        on_tx,
    ) -> None:
        super().__init__(daemon=True, name=f"pgn-{arb_id:08X}")
        self._bus = bus
        self._arb_id = arb_id
        self._period_fn = period_fn
        self._data_fn = data_fn
        self._on_tx = on_tx
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        next_t = time.monotonic()
        while not self._stop.is_set():
            data = self._data_fn()
            msg = can.Message(
                arbitration_id=self._arb_id,
                data=data,
                is_extended_id=True,
                dlc=min(8, len(data)),
            )
            try:
                self._bus.send(msg, timeout=0.5)
                self._on_tx()
            except Exception:
                if self._stop.is_set():
                    break
            period = max(0.001, float(self._period_fn()))
            next_t += period
            delay = next_t - time.monotonic()
            if delay > 0:
                self._stop.wait(delay)
            else:
                next_t = time.monotonic()


@dataclass
class EmulatorSession:
    """Single-channel emulation session for v1.0 (1 ECU SA 0x00)."""

    signals: SignalState = field(default_factory=SignalState)
    identity: EcuIdentity = field(default_factory=EcuIdentity)
    diagnostics: DiagnosticState = field(default_factory=DiagnosticState)
    bitrate: int = 500_000
    mode: EmulationMode = EmulationMode.VIRTUAL

    _bus: can.BusABC | None = field(default=None, init=False, repr=False)
    _ecu: ElectronicControlUnit | None = field(default=None, init=False, repr=False)
    _ca: ControllerApplication | None = field(default=None, init=False, repr=False)
    _dm1: Dm1 | None = field(default=None, init=False, repr=False)
    _dm1_sending: bool = field(default=False, init=False)
    _senders: list[_PeriodicSender] = field(default_factory=list, init=False, repr=False)
    _channel: DetectedChannel | None = field(default=None, init=False, repr=False)
    _running: bool = field(default=False, init=False)
    _started_at: float | None = field(default=None, init=False)
    _tx_count: int = field(default=0, init=False)
    _frozen_uptime: float = field(default=0.0, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    _tx_window_start: float = field(default=0.0, init=False)
    _tx_window_count: int = field(default=0, init=False)
    _load_pct: float = field(default=0.0, init=False)

    @property
    def running(self) -> bool:
        return self._running

    @property
    def channel(self) -> DetectedChannel | None:
        return self._channel

    @property
    def address_claimed(self) -> bool:
        if self._ca is None:
            return False
        return self._ca.state == ControllerApplication.State.NORMAL

    def stats(self) -> SessionStats:
        with self._lock:
            if self._running and self._started_at is not None:
                uptime = time.monotonic() - self._started_at
                self._update_load_locked()
            else:
                uptime = self._frozen_uptime
            label = self._channel.label if self._channel else ""
            return SessionStats(
                running=self._running,
                uptime_s=uptime,
                tx_count=self._tx_count,
                load_pct=0.0 if not self._running else self._load_pct,
                bitrate=self.bitrate,
                mode=self.mode,
                channel_label=label,
                sa=self.identity.source_address & 0xFF,
                active_dtcs=self.diagnostics.active_count,
                address_claimed=self.address_claimed if self._running else False,
            )

    def start(self, channel: DetectedChannel, bitrate: int | None = None) -> None:
        with self._lock:
            if self._running:
                self._stop_locked()
            if bitrate is not None:
                self.bitrate = int(bitrate)
            self._begin_locked(channel)

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def reset(self, channel: DetectedChannel | None = None, bitrate: int | None = None) -> None:
        with self._lock:
            ch = channel or self._channel
            if ch is None:
                raise RuntimeError("No channel selected for RESET")
            if bitrate is not None:
                self.bitrate = int(bitrate)
            self._stop_locked()
            self._begin_locked(ch)

    def set_vin(self, vin: str) -> str:
        """Update VIN; re-broadcast VI while running."""
        cleaned = self.identity.set_vin(vin)
        with self._lock:
            if self._running and self._ca is not None and self.address_claimed:
                self._broadcast_vin_locked()
        return cleaned

    def set_dtc1(self, active: bool) -> None:
        self.diagnostics.set_dtc1(active)
        with self._lock:
            self._sync_dm1_locked()

    def set_dtc2(self, active: bool) -> None:
        self.diagnostics.set_dtc2(active)
        with self._lock:
            self._sync_dm1_locked()

    def set_dtcs(self, dtc1: bool | None = None, dtc2: bool | None = None) -> None:
        if dtc1 is not None:
            self.diagnostics.dtc_spn110_fmi3 = bool(dtc1)
        if dtc2 is not None:
            self.diagnostics.dtc_spn190_fmi0 = bool(dtc2)
        self.diagnostics.notify()
        with self._lock:
            self._sync_dm1_locked()

    def clear_all_dtcs(self) -> None:
        self.diagnostics.clear_all()
        with self._lock:
            self._sync_dm1_locked()

    def inject_both_dtcs(self) -> None:
        self.diagnostics.inject_both()
        with self._lock:
            self._sync_dm1_locked()

    def _bus_kwargs(self, channel: DetectedChannel) -> dict[str, Any]:
        kwargs = dict(channel.bus_kwargs)
        if channel.interface != "virtual":
            kwargs.setdefault("bitrate", self.bitrate)
        if kwargs.get("interface") == "vector":
            kwargs.setdefault("app_name", "python-can")
        # Own claim frames need not echo; peer tests use a second Bus.
        kwargs.setdefault("receive_own_messages", False)
        return kwargs

    def _begin_locked(self, channel: DetectedChannel) -> None:
        self.mode = channel.kind
        self._channel = channel
        self._ecu = ElectronicControlUnit()
        try:
            self._bus = self._ecu.connect(**self._bus_kwargs(channel))
        except Exception:
            try:
                self._ecu.stop()
            except Exception:
                pass
            self._ecu = None
            self._bus = None
            raise

        name = Name(value=int(self.identity.name))
        self._ca = ControllerApplication(
            name, device_address_preferred=int(self.identity.source_address) & 0xFF
        )
        self._ecu.add_ca(controller_application=self._ca)
        self._ca.start()
        try:
            self._wait_claim_locked(timeout_s=1.5)
        except Exception:
            self._stop_locked()
            raise

        self._started_at = time.monotonic()
        self._tx_count = 0
        self._tx_window_start = self._started_at
        self._tx_window_count = 0
        self._load_pct = 0.0
        self._frozen_uptime = 0.0
        self._running = True
        self._dm1 = Dm1(self._ca)
        self._dm1_sending = False
        self._start_senders_locked()
        self._broadcast_vin_locked()
        self._sync_dm1_locked()

    def _wait_claim_locked(self, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._ca is not None and self._ca.state == ControllerApplication.State.NORMAL:
                return
            # Release lock briefly so claim timer thread can progress cleanly
            self._lock.release()
            try:
                time.sleep(0.05)
            finally:
                self._lock.acquire()
        if self._ca is None or self._ca.state != ControllerApplication.State.NORMAL:
            raise RuntimeError(
                f"Address claim failed for SA 0x{self.identity.source_address:02X}"
            )

    def _broadcast_vin_locked(self) -> None:
        if self._ca is None:
            return
        payload = self.identity.vin_payload()
        self._ca.send_pgn(0, VI_PDU_FORMAT, VI_PDU_SPECIFIC, VI_PRIORITY, payload)
        # BAM uses multiple frames; count as one logical TX
        self._on_tx()

    def _sync_dm1_locked(self) -> None:
        if not self._running or self._dm1 is None or self._ca is None:
            return
        active = self.diagnostics.active_count > 0
        if active and not self._dm1_sending:
            self._dm1.start_send(
                self.diagnostics.dm1_callback, cycletime=DM1_CYCLE_MS / 1000.0
            )
            self._dm1_sending = True
        elif not active and self._dm1_sending:
            try:
                self._dm1.stop_send(self._dm1._send)
            except Exception:
                pass
            self._dm1_sending = False

    def _stop_locked(self) -> None:
        if self._started_at is not None and self._running:
            self._frozen_uptime = time.monotonic() - self._started_at

        if self._dm1 is not None and self._dm1_sending:
            try:
                self._dm1.stop_send(self._dm1._send)
            except Exception:
                pass
        self._dm1_sending = False
        self._dm1 = None

        if self._ca is not None:
            try:
                self._ca.stop()
            except Exception:
                pass
            self._ca = None

        for sender in self._senders:
            sender.stop()
        for sender in self._senders:
            sender.join(timeout=1.5)
        self._senders.clear()

        if self._ecu is not None:
            try:
                if self._bus is not None:
                    self._ecu.disconnect()
            except Exception:
                pass
            try:
                self._ecu.stop()
            except Exception:
                pass
            self._ecu = None
            self._bus = None

        self._running = False
        self._load_pct = 0.0
        self._started_at = None

    def _ms(self, getter: Callable[[], int]) -> Callable[[], float]:
        return lambda: max(1, int(getter())) / 1000.0

    def _start_senders_locked(self) -> None:
        assert self._bus is not None
        s = self.signals
        specs = [
            (s.eec1_enabled, CAN_ID_EEC1, self._ms(lambda: s.cycle_eec1_ms), lambda: encode_eec1(s)),
            (s.ccvs_enabled, CAN_ID_CCVS, self._ms(lambda: s.cycle_ccvs_ms), lambda: encode_ccvs(s)),
            (s.fuel_enabled, CAN_ID_FUEL, self._ms(lambda: s.cycle_fuel_ms), lambda: encode_fuel(s)),
            (s.et1_enabled, CAN_ID_ET1, self._ms(lambda: s.cycle_et1_ms), lambda: encode_et1(s)),
            (s.vd_enabled, CAN_ID_VD, self._ms(lambda: s.cycle_vd_ms), lambda: encode_vd(s)),
        ]
        for enabled, arb_id, period_fn, data_fn in specs:
            if not enabled:
                continue
            sender = _PeriodicSender(self._bus, arb_id, period_fn, data_fn, self._on_tx)
            self._senders.append(sender)
            sender.start()

    def _on_tx(self) -> None:
        with self._lock:
            self._tx_count += 1
            self._tx_window_count += 1
            self._update_load_locked()

    def _update_load_locked(self) -> None:
        now = time.monotonic()
        elapsed = now - self._tx_window_start
        if elapsed >= 0.5:
            bps = (self._tx_window_count * _BITS_PER_FRAME) / max(elapsed, 1e-6)
            self._load_pct = min(100.0, (bps / max(self.bitrate, 1)) * 100.0)
            self._tx_window_start = now
            self._tx_window_count = 0
        elif self._running and self._load_pct <= 0.0 and self._tx_count > 0:
            hz = 0.0
            s = self.signals
            if s.eec1_enabled:
                hz += 1000.0 / max(1, s.cycle_eec1_ms)
            if s.ccvs_enabled:
                hz += 1000.0 / max(1, s.cycle_ccvs_ms)
            if s.fuel_enabled:
                hz += 1000.0 / max(1, s.cycle_fuel_ms)
            if s.et1_enabled:
                hz += 1000.0 / max(1, s.cycle_et1_ms)
            if s.vd_enabled:
                hz += 1000.0 / max(1, s.cycle_vd_ms)
            if self.diagnostics.active_count > 0:
                hz += 1.0
            self._load_pct = min(100.0, (hz * _BITS_PER_FRAME / max(self.bitrate, 1)) * 100.0)
