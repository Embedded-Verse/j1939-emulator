"""NiceGUI application matching standalone_v1.0.html (M1: Bus + Signals)."""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from typing import Any

from nicegui import app, ui

from j1939_emulator.bus.detect import DetectedChannel, EmulationMode, detect_hardware
from j1939_emulator.bus.session import EmulatorSession
from j1939_emulator.config import load_config
from j1939_emulator.gui.styles import APP_CSS
from j1939_emulator.gui.widgets import (
    build_ccvs,
    build_diagnostics_pane,
    build_ecu_pane,
    build_eec1,
    build_et1,
    build_fuel,
    build_vd,
)
from j1939_emulator.pgn import SignalState, all_payloads
from j1939_emulator.diagnostics import DiagnosticState
from j1939_emulator.ecu_identity import EcuIdentity

BITRATE_OPTIONS = {
    "125 kbit/s": 125_000,
    "250 kbit/s (Traditional / Common)": 250_000,
    "500 kbit/s (J1939 / Modern)": 500_000,
    "1000 kbit/s (FD)": 1_000_000,
}

MODE_OPTIONS = {
    "Real Hardware Emulation": EmulationMode.REAL,
    "Virtual Emulation": EmulationMode.VIRTUAL,
}

PGN_SEARCH = {
    "eec1": "eec1 61444 rpm torque engine starter mode spn190 spn513 spn512 spn899",
    "ccvs": "ccvs 65265 speed cruise brake clutch spn84 spn595 spn597 spn598",
    "fuel": "fuel 65266 economy rate throttle pedal spn183 spn184 spn91",
    "et1": "et1 65262 temperature coolant oil fuel spn110 spn175 spn174",
    "vd": "vd 65248 distance odometer trip vehicle spn917 spn918",
}


class GuiState:
    def __init__(self, session: EmulatorSession) -> None:
        self.session = session
        self.mode = EmulationMode.VIRTUAL
        self.channels: list[DetectedChannel] = []
        self.channel_uid: str | None = None
        self.bitrate = 500_000
        self.payload_labels: dict[str, Any] = {}
        self.pgn_containers: dict[str, Any] = {}
        self.ui_refs: dict[str, Any] = {}
        self.host = "127.0.0.1"
        self.port = 8080
        self.config_path: str | None = None
        self.open_browser = True
        self._relaunch: dict[str, Any] | None = None


def run_gui(
    config_path: str | None = None,
    host: str = "127.0.0.1",
    port: int = 8080,
    open_browser: bool = True,
) -> None:
    signals = SignalState()
    identity = EcuIdentity()
    diagnostics = DiagnosticState()
    bitrate = 500_000
    mode = EmulationMode.VIRTUAL
    preferred_channel: str | None = None

    if config_path:
        cfg = load_config(config_path)
        signals = cfg.signals
        identity = cfg.identity
        diagnostics = cfg.diagnostics
        bitrate = cfg.bus.bitrate
        mode = cfg.bus.mode
        preferred_channel = cfg.bus.channel

    session = EmulatorSession(
        signals=signals,
        identity=identity,
        diagnostics=diagnostics,
        bitrate=bitrate,
        mode=mode,
    )
    state = GuiState(session)
    state.mode = mode
    state.bitrate = bitrate
    state.host = host
    state.port = int(port)
    state.config_path = config_path
    state.open_browser = open_browser

    @app.on_startup
    def _startup() -> None:
        state.channels = detect_hardware(mode=state.mode, timeout=6.0)
        if preferred_channel:
            for ch in state.channels:
                if preferred_channel in (ch.uid, str(ch.bus_kwargs.get("channel")), ch.label):
                    state.channel_uid = ch.uid
                    break
        if state.channel_uid is None and state.channels:
            state.channel_uid = state.channels[0].uid
        if state.open_browser:
            url = f"http://{state.host}:{state.port}/"
            try:
                webbrowser.open(url)
            except Exception:
                pass

    @app.on_shutdown
    def _shutdown() -> None:
        session.stop()

    @ui.page("/")
    def index_page() -> None:
        ui.add_css(APP_CSS)
        _build_page(state, preferred_channel)

    ui.run(
        host=host,
        port=port,
        title="SAE J1939 Heavy-Duty Vehicle Emulator",
        reload=False,
        show=False,
    )

    if state._relaunch:
        _relaunch_gui(state._relaunch)


def _relaunch_gui(opts: dict[str, Any]) -> None:
    """Restart the GUI process on a new host/port after Apply Port."""
    cmd = [
        sys.executable,
        "-m",
        "j1939_emulator",
        "--gui",
        "--host",
        str(opts["host"]),
        "--port",
        str(opts["port"]),
    ]
    if opts.get("config_path"):
        cmd.extend(["--config", str(opts["config_path"])])
    if not opts.get("open_browser", True):
        cmd.append("--no-browser")
    kwargs: dict[str, Any] = {"cwd": os.getcwd()}
    if sys.platform == "win32":
        # Keep a visible console for the restarted server.
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(cmd, **kwargs)


def _selected_channel(state: GuiState) -> DetectedChannel | None:
    for ch in state.channels:
        if ch.uid == state.channel_uid:
            return ch
    return None


def _fmt_uptime(seconds: float) -> str:
    s = int(max(0, seconds))
    return f"{s // 60:02d}:{s % 60:02d}"


def _bitrate_label(bitrate: int) -> str:
    for label, value in BITRATE_OPTIONS.items():
        if value == bitrate:
            return label
    return f"{bitrate} bit/s"


def _build_page(state: GuiState, preferred_channel: str | None) -> None:
    session = state.session
    sig = session.signals

    with ui.element("div").classes("j1939-root"):
        with ui.element("header").classes("topbar"):
            with ui.element("div").classes("brand-section"):
                ui.label("J").classes("brand-icon")
                ui.label("SAE J1939 Heavy-Duty Vehicle Emulator").classes("brand-title")
                ui.label("v1.0").classes("badge-subtle font-mono")
            with ui.row().classes("items-center gap-3 flex-wrap"):
                top_pill = ui.element("span").classes("status-pill stopped font-mono")
                with top_pill:
                    ui.element("span").classes("status-dot")
                    top_status = ui.label("ECU STOPPED")
                port_badge = ui.label(f"PORT :{state.port} READY").classes(
                    "badge-subtle font-mono"
                ).style("background:#F8FAFC; color:#5B6775; border-color:#CBD5E1;")
                with ui.row().classes("items-center gap-1"):
                    ui.label("Host").classes("field-label").style("margin:0;")
                    host_input = (
                        ui.input(value=state.host)
                        .props("dense outlined")
                        .style("width:120px")
                        .classes("font-mono")
                    )
                    ui.label("Port").classes("field-label").style("margin:0;")
                    port_input = (
                        ui.number(
                            value=state.port, min=1, max=65535, step=1, format="%.0f"
                        )
                        .props("dense outlined")
                        .style("width:90px")
                        .classes("font-mono")
                    )
                    btn_apply_port = ui.button("Apply").props("flat dense")
                btn_quit = (
                    ui.button("QUIT")
                    .classes("action-btn btn-quit font-mono")
                    .props("unelevated dense")
                )

        with ui.element("main").classes("j1939-main"):
            with ui.element("section").classes("card bus-bar"):
                with ui.element("div").classes("bus-controls-group"):
                    ui.label("Bus Config").style(
                        "font-weight:800;font-size:11px;color:#5B6775;text-transform:uppercase;"
                        "border-right:1px solid #CBD5E1;padding-right:8px;"
                    )
                    with ui.column().classes("gap-0"):
                        ui.label("Emulation Mode").classes("field-label")
                        mode_select = ui.select(
                            options=list(MODE_OPTIONS.keys()),
                            value=next(k for k, v in MODE_OPTIONS.items() if v == state.mode),
                        ).props("dense outlined options-dense").style("min-width:220px")

                    with ui.column().classes("gap-0"):
                        ui.label("Interface / Channel").classes("field-label")
                        channel_select = ui.select(options={}, value=None).props(
                            "dense outlined options-dense"
                        ).style("min-width:260px")

                    with ui.column().classes("gap-0"):
                        ui.label("Bitrate").classes("field-label")
                        bitrate_select = ui.select(
                            options=list(BITRATE_OPTIONS.keys()),
                            value=_bitrate_label(state.bitrate),
                        ).props("dense outlined options-dense").style("width:160px")

                    refresh_btn = ui.button("Refresh").props("flat dense")

                with ui.row().classes("items-center gap-2"):
                    btn_start = ui.button("START").classes(
                        "action-btn btn-start font-mono"
                    ).props("unelevated dense")
                    btn_stop = ui.button("STOP").classes(
                        "action-btn btn-stop font-mono"
                    ).props("unelevated dense outline")
                    btn_reset = ui.button("RESET").classes(
                        "action-btn btn-restart font-mono"
                    ).props("unelevated dense outline")
                    with ui.row().classes("items-center gap-3 font-mono").style(
                        "margin-left:12px;font-size:11px;"
                    ):
                        ui.label("Uptime:")
                        stat_uptime = ui.label("00:00").style(
                            "font-weight:700;color:#1F2A37"
                        )
                        ui.label("|").style("color:#CBD5E1")
                        ui.label("TX:")
                        stat_tx = ui.label("0").style("font-weight:700;color:#1F9D55")
                        ui.label("|").style("color:#CBD5E1")
                        ui.label("Load:")
                        stat_load = ui.label("0.0%").style(
                            "font-weight:700;color:#1F2A37"
                        )

            with ui.element("nav").classes("tab-bar font-mono"):
                tab_signals = ui.button().classes("tab-btn active").props("flat dense")
                with tab_signals:
                    ui.label("Signals (PGNs & SPNs)")
                    ui.label("5 PGNs").classes("tab-pill")
                tab_ecu = ui.button().classes("tab-btn").props("flat dense")
                with tab_ecu:
                    ui.label("ECU & Vehicle (VIN)")
                    ui.label("Node 0x00").classes("tab-pill")
                tab_diag = ui.button().classes("tab-btn").props("flat dense")
                with tab_diag:
                    ui.label("Diagnostics (2 DTCs)")
                    diag_tab_pill = ui.label("2 Supported").classes("tab-pill")
                    state.ui_refs["diag_tab_pill"] = diag_tab_pill

            pane_signals = ui.element("section")
            with pane_signals:
                with ui.row().classes("w-full items-center justify-between").style(
                    "margin-bottom:10px;"
                ):
                    search_input = (
                        ui.input(
                            placeholder="Search PGN or SPN (e.g. 190, 84, 183, 110, 917)..."
                        )
                        .props("dense outlined clearable")
                        .style("width:340px")
                        .classes("font-mono")
                    )
                    ui.label(
                        "SAE J1939-71 Application Layer · Real-Time 5 PGN CAN Broadcast"
                    ).classes("font-mono").style("font-size:11px;color:#5B6775;")

                state.payload_labels.clear()
                state.pgn_containers.clear()
                sig.clear_listeners()

                build_eec1(sig, state.payload_labels, state.pgn_containers)
                build_ccvs(sig, state.payload_labels, state.pgn_containers)
                build_fuel(sig, state.payload_labels, state.pgn_containers)
                build_et1(sig, state.payload_labels, state.pgn_containers)
                build_vd(sig, state.payload_labels, state.pgn_containers)

            pane_ecu = ui.element("section")
            with pane_ecu:
                build_ecu_pane(session, state.ui_refs)
            pane_ecu.set_visibility(False)

            pane_diag = ui.element("section")
            with pane_diag:
                build_diagnostics_pane(session, state.ui_refs)
            pane_diag.set_visibility(False)

        with ui.element("footer").classes("j1939-footer"):
            with ui.element("div").classes("footer-left font-mono"):
                foot_status = ui.label("● ECU STOPPED")
                foot_sa = ui.label("SA: 0x00")
                foot_bitrate = ui.label(f"{state.bitrate // 1000} kbit/s")
            with ui.row().classes("items-center gap-3 font-mono"):
                foot_tx = ui.label("TX Broadcast: 0 frames")
                foot_dtc = ui.label("Active Faults: 0 DTCs").style("color:#1F9D55")
                state.ui_refs["foot_dtc"] = foot_dtc
                ui.label("SAE J1939 v1.0").style("color:#1F9D55;font-weight:700;")

    def refresh_channels() -> None:
        state.channels = detect_hardware(mode=state.mode, timeout=6.0)
        options = {ch.uid: ch.label for ch in state.channels}
        channel_select.options = options
        if preferred_channel and state.channel_uid is None:
            for ch in state.channels:
                if preferred_channel in (
                    ch.uid,
                    str(ch.bus_kwargs.get("channel")),
                    ch.label,
                ):
                    state.channel_uid = ch.uid
                    break
        if state.channel_uid not in options:
            state.channel_uid = next(iter(options), None)
        channel_select.value = state.channel_uid
        channel_select.update()

    def on_mode_change(e) -> None:
        label = e.value if hasattr(e, "value") else mode_select.value
        new_mode = MODE_OPTIONS.get(label, EmulationMode.VIRTUAL)
        if new_mode is state.mode and state.channels:
            return
        if session.running:
            session.stop()
            update_chrome()
        state.mode = new_mode
        refresh_channels()

    def on_channel_change(e) -> None:
        state.channel_uid = e.value if hasattr(e, "value") else channel_select.value

    def on_bitrate_change(e) -> None:
        label = e.value if hasattr(e, "value") else bitrate_select.value
        state.bitrate = BITRATE_OPTIONS.get(label, 500_000)
        foot_bitrate.set_text(f"{state.bitrate // 1000} kbit/s")

    def do_start() -> None:
        ch = _selected_channel(state)
        if ch is None:
            ui.notify("No channel selected", type="warning")
            return
        try:
            session.start(ch, bitrate=state.bitrate)
            update_chrome()
            ui.notify(f"Started on {ch.label}", type="positive")
        except Exception as exc:
            ui.notify(f"START failed: {exc}", type="negative")

    def do_stop() -> None:
        session.stop()
        update_chrome()

    def do_reset() -> None:
        ch = _selected_channel(state) or session.channel
        if ch is None:
            ui.notify("No channel selected", type="warning")
            return
        try:
            session.reset(ch, bitrate=state.bitrate)
            update_chrome()
            ui.notify("RESET", type="info")
        except Exception as exc:
            ui.notify(f"RESET failed: {exc}", type="negative")

    def do_quit() -> None:
        session.stop()
        ui.notify("Shutting down…", type="info")
        app.shutdown()

    def do_apply_listen() -> None:
        raw_host = (host_input.value or "").strip() or "127.0.0.1"
        try:
            new_port = int(port_input.value)
        except (TypeError, ValueError):
            ui.notify("Port must be an integer 1–65535", type="negative")
            return
        if not (1 <= new_port <= 65535):
            ui.notify("Port must be between 1 and 65535", type="negative")
            return
        if raw_host == state.host and new_port == state.port:
            ui.notify(
                f"Already listening on http://{state.host}:{state.port}/", type="info"
            )
            return
        state._relaunch = {
            "host": raw_host,
            "port": new_port,
            "config_path": state.config_path,
            "open_browser": state.open_browser,
        }
        session.stop()
        ui.notify(f"Restarting on http://{raw_host}:{new_port}/ …", type="info")
        app.shutdown()

    def switch_tab(name: str) -> None:
        pane_signals.set_visibility(name == "signals")
        pane_ecu.set_visibility(name == "ecu")
        pane_diag.set_visibility(name == "diagnostics")
        for btn, key in (
            (tab_signals, "signals"),
            (tab_ecu, "ecu"),
            (tab_diag, "diagnostics"),
        ):
            btn.classes(remove="active")
            if key == name:
                btn.classes(add="active")

    def filter_signals(e=None) -> None:
        if e is not None and hasattr(e, "value"):
            raw = e.value
        else:
            raw = search_input.value
        q = ("" if raw is None else str(raw)).strip().lower()
        for key, container in state.pgn_containers.items():
            terms = PGN_SEARCH[key]
            visible = (not q) or (q in terms)
            if visible:
                container.classes(remove="pgn-hidden")
                container.style("display: block;")
            else:
                container.classes(add="pgn-hidden")
                container.style("display: none;")

    def update_chrome() -> None:
        st = session.stats()
        if st.running:
            top_pill.classes(remove="stopped", add="running")
            top_status.set_text("EMULATING · RUNNING")
            foot_status.set_text("● ECU Emulating")
            btn_start.disable()
            btn_stop.enable()
        else:
            top_pill.classes(remove="running", add="stopped")
            top_status.set_text("ECU STOPPED")
            foot_status.set_text("● ECU STOPPED")
            btn_start.enable()
            btn_stop.disable()
        claim_chip = state.ui_refs.get("claim_chip")
        claim_label = state.ui_refs.get("claim_label")
        if claim_chip is not None and claim_label is not None:
            if st.running and st.address_claimed:
                claim_chip.classes(remove="stopped", add="running")
                claim_label.set_text("NODE ONLINE · CLAIMED")
            else:
                claim_chip.classes(remove="running", add="stopped")
                claim_label.set_text("NODE OFFLINE")
        port_badge.set_text(f"PORT :{state.port} READY")
        stat_uptime.set_text(_fmt_uptime(st.uptime_s))
        stat_tx.set_text(str(st.tx_count))
        load = 0.0 if not st.running else st.load_pct
        stat_load.set_text(f"{load:.1f}%")
        foot_tx.set_text(f"TX Broadcast: {st.tx_count} frames")
        foot_bitrate.set_text(f"{st.bitrate // 1000} kbit/s")
        foot_sa.set_text(f"SA: 0x{st.sa:02X}")
        c = st.active_dtcs
        if c > 0:
            foot_dtc.set_text(f"Active Faults: {c} DTCs")
            foot_dtc.style("color:#B45309")
        else:
            foot_dtc.set_text("Active Faults: 0 DTCs")
            foot_dtc.style("color:#1F9D55")
        pill = state.ui_refs.get("diag_tab_pill")
        if pill is not None:
            if c > 0:
                pill.set_text(f"{c} Active")
                pill.classes(add="warn")
            else:
                pill.set_text("2 Supported")
                pill.classes(remove="warn")

    def refresh_payloads() -> None:
        payloads = all_payloads(sig)
        for key, label in state.payload_labels.items():
            label.set_text(payloads[key])
            try:
                label.update()
            except Exception:
                pass

    sig.clear_listeners()
    sig.on_change(refresh_payloads)

    mode_select.on_value_change(on_mode_change)
    channel_select.on_value_change(on_channel_change)
    bitrate_select.on_value_change(on_bitrate_change)
    search_input.on_value_change(filter_signals)
    search_input.on("keyup", lambda _: filter_signals())
    refresh_btn.on_click(refresh_channels)
    btn_start.on_click(do_start)
    btn_stop.on_click(do_stop)
    btn_reset.on_click(do_reset)
    btn_quit.on_click(do_quit)
    btn_apply_port.on_click(do_apply_listen)
    tab_signals.on_click(lambda: switch_tab("signals"))
    tab_ecu.on_click(lambda: switch_tab("ecu"))
    tab_diag.on_click(lambda: switch_tab("diagnostics"))

    ui.timer(0.2, update_chrome)

    def _init_channels() -> None:
        refresh_channels()
        btn_stop.disable()
        refresh_payloads()

    ui.timer(0.3, _init_channels, once=True)
