"""Reusable SPN control widgets for the NiceGUI Signals tab."""

from __future__ import annotations

from typing import Any, Callable

from nicegui import ui

from j1939_emulator.pgn import (
    STARTER_LABELS,
    SignalState,
    encode_ccvs,
    encode_eec1,
    encode_et1,
    encode_fuel,
    encode_vd,
    payload_hex,
)


def slider_spn(
    spn: str,
    name: str,
    unit: str,
    initial: float,
    min_v: float,
    max_v: float,
    step: float,
    on_change: Callable[[float], None],
    presets: list[tuple[str, float]] | None = None,
    decimals: int | None = None,
    number_step: float | None = None,
) -> Any:
    with ui.element("div").classes("signal-box"):
        with ui.element("div").classes("signal-top font-mono"):
            with ui.row().classes("items-center"):
                ui.label(spn).classes("spn-badge")
                ui.label(name).classes("signal-name")
            with ui.row().classes("items-center gap-1"):
                if decimals is not None:
                    disp = ui.label(f"{float(initial):.{decimals}f}").classes("signal-val")
                else:
                    v = float(initial)
                    disp = ui.label(str(int(v)) if v == int(v) else str(v)).classes("signal-val")
                ui.label(unit).style("font-size:11px;color:#5B6775;")
        with ui.element("div").classes("range-row"):
            slider = ui.slider(min=min_v, max=max_v, step=step, value=initial).classes("w-full")
            num = ui.number(
                value=initial,
                min=min_v,
                max=max_v,
                step=number_step if number_step is not None else step,
            ).props("dense outlined").style("width:90px")

        def apply(val) -> None:
            try:
                num_v = float(val)
            except (TypeError, ValueError):
                return
            num_v = max(min_v, min(max_v, num_v))
            slider.value = num_v
            num.value = num_v
            if decimals is not None:
                disp.set_text(f"{num_v:.{decimals}f}")
            else:
                disp.set_text(str(int(num_v)) if num_v == int(num_v) else str(num_v))
            on_change(num_v)

        slider.on_value_change(lambda e: apply(e.value))
        num.on_value_change(lambda e: apply(e.value))

        if presets:
            with ui.row().classes("w-full justify-between font-mono").style(
                "font-size:10px;color:#5B6775;"
            ):
                ui.label(f"Min: {min_v} {unit}")
                with ui.row().classes("gap-1 items-center"):
                    ui.label("Presets:")
                    for label, val in presets:
                        ui.button(label, on_click=lambda v=val: apply(v)).classes(
                            "preset-btn"
                        ).props("flat dense")
                ui.label(f"Max: {max_v} {unit}")
    return disp


def bool_toggle(spn: str, name: str, getter, setter) -> None:
    with ui.element("div").classes("signal-box"):
        with ui.element("div").classes("signal-top font-mono"):
            with ui.row().classes("items-center"):
                ui.label(spn).classes("spn-badge")
                ui.label(name).classes("signal-name")
            disp = ui.label("ACTIVE / ON" if getter() else "INACTIVE / OFF").classes("signal-val")
        with ui.row().classes("items-center justify-between w-full"):
            ui.label("Discrete Switch Status:").style("font-size:11px;color:#5B6775;")
            with ui.row().classes("gap-1 font-mono"):
                btn_off = ui.button("Inactive (0)").classes("toggle-btn")
                btn_on = ui.button("Active (1)").classes("toggle-btn")

                def set_off() -> None:
                    setter(False)
                    disp.set_text("INACTIVE / OFF")
                    btn_off.classes(add="off-active")
                    btn_on.classes(remove="active")

                def set_on() -> None:
                    setter(True)
                    disp.set_text("ACTIVE / ON")
                    btn_on.classes(add="active")
                    btn_off.classes(remove="off-active")

                btn_off.on_click(set_off)
                btn_on.on_click(set_on)
                if getter():
                    btn_on.classes(add="active")
                else:
                    btn_off.classes(add="off-active")


def pgn_header(
    acronym: str,
    title: str,
    pgn_badge: str,
    can_id: str,
    cycle_ms: int,
    on_cycle: Callable[[int], None],
) -> None:
    with ui.element("div").classes("pgn-header"):
        with ui.element("div").classes("pgn-title-group"):
            ui.label(acronym).classes("badge-acronym font-mono")
            ui.label(title).classes("pgn-name")
            ui.label(pgn_badge).classes("badge-subtle font-mono")
            ui.label(can_id).classes("badge-subtle font-mono").style(
                "background:#F1F5F9;color:#5B6775;border-color:#CBD5E1;"
            )
        with ui.row().classes("items-center gap-2 font-mono").style("font-size:11px;color:#5B6775;"):
            ui.label("Cycle:")
            cycle_input = ui.number(value=cycle_ms, min=1, max=60000, step=1).props(
                "dense outlined"
            ).style("width:80px")
            ui.label("ms").style("font-weight:700;color:#1F2A37;")

            def apply_cycle(e) -> None:
                try:
                    ms = int(float(e.value))
                except (TypeError, ValueError):
                    return
                ms = max(1, min(60000, ms))
                cycle_input.value = ms
                on_cycle(ms)

            cycle_input.on_value_change(apply_cycle)


def payload_strip(priority: int, hex_text: str) -> Any:
    with ui.element("div").classes("payload-strip font-mono"):
        with ui.row().classes("items-center gap-2"):
            ui.label("CAN Payload:")
            label = ui.label(hex_text).classes("signal-val").style(
                "font-weight:700;color:#1F2A37;letter-spacing:0.04em;"
            )
        ui.label(f"DLC: 8 Bytes · Priority: {priority}").style("color:#64748B;")
    return label


def _bind(sig: SignalState, attr: str) -> Callable[[float], None]:
    def _set(v: float) -> None:
        setattr(sig, attr, float(v))
        sig.notify()

    return _set


def build_eec1(sig: SignalState, payload_labels: dict, containers: dict) -> None:
    card = ui.element("div").classes("pgn-card")
    containers["eec1"] = card
    with card:
        pgn_header(
            "EEC1",
            "Electronic Engine Controller 1",
            "PGN 61444 (0x00F004)",
            "CAN ID: 0x0CF00400",
            sig.cycle_eec1_ms,
            lambda ms: (setattr(sig, "cycle_eec1_ms", ms), sig.notify()),
        )
        payload_labels["eec1"] = payload_strip(3, payload_hex(encode_eec1(sig)))
        slider_spn(
            "SPN 190", "Engine Speed", "rpm", sig.spn190_rpm, 0, 3500, 25,
            _bind(sig, "spn190_rpm"),
            presets=[("Idle 650", 650), ("Cruise 1250", 1250), ("Rated 2100", 2100)],
        )
        slider_spn(
            "SPN 513", "Actual Engine % Torque", "%", sig.spn513_torque_pct, -125, 125, 1,
            _bind(sig, "spn513_torque_pct"),
        )
        slider_spn(
            "SPN 512", "Driver Demand % Torque", "%", sig.spn512_demand_torque_pct, -125, 125, 1,
            _bind(sig, "spn512_demand_torque_pct"),
        )
        with ui.element("div").classes("signal-box"):
            with ui.element("div").classes("signal-top font-mono"):
                with ui.row().classes("items-center"):
                    ui.label("SPN 899").classes("spn-badge")
                    ui.label("Engine Starter Mode").classes("signal-name")
                disp899 = ui.label(sig.starter_label()).classes("signal-val").style(
                    "color:#1F6FEB;"
                )
            with ui.row().classes("items-center justify-between w-full flex-wrap gap-2"):
                ui.label("Operating State Selector (SAE J1939 Discrete Mode):").style(
                    "font-size:11px;color:#5B6775;"
                )
                btns: dict[int, Any] = {}
                with ui.row().classes("gap-2 font-mono"):

                    def make_starter(code: int, label: str) -> None:
                        def _click() -> None:
                            sig.spn899_starter_mode = code
                            sig.notify()
                            disp899.set_text(STARTER_LABELS[code])
                            for c, b in btns.items():
                                b.classes(remove="active")
                                if c == code:
                                    b.classes(add="active")

                        b = ui.button(label, on_click=_click).classes("toggle-btn")
                        if code == sig.spn899_starter_mode:
                            b.classes(add="active")
                        btns[code] = b

                    make_starter(3, "Start Finished")
                    make_starter(0, "Start Not Requested")
                    make_starter(4, "Engine Cranking")
                    make_starter(2, "Starter Active")


def build_ccvs(sig: SignalState, payload_labels: dict, containers: dict) -> None:
    card = ui.element("div").classes("pgn-card")
    containers["ccvs"] = card
    with card:
        pgn_header(
            "CCVS",
            "Cruise Control / Vehicle Speed",
            "PGN 65265 (0x00FEF1)",
            "CAN ID: 0x18FEF100",
            sig.cycle_ccvs_ms,
            lambda ms: (setattr(sig, "cycle_ccvs_ms", ms), sig.notify()),
        )
        payload_labels["ccvs"] = payload_strip(6, payload_hex(encode_ccvs(sig)))
        slider_spn(
            "SPN 84", "Wheel-Based Vehicle Speed", "mph", sig.spn84_speed_mph, 0, 120, 0.5,
            _bind(sig, "spn84_speed_mph"),
            presets=[("0 mph", 0), ("35 mph", 35), ("65 mph", 65)],
            decimals=1,
        )
        bool_toggle(
            "SPN 595", "Cruise Control Active",
            lambda: sig.spn595_cruise,
            lambda on: (setattr(sig, "spn595_cruise", on), sig.notify()),
        )
        bool_toggle(
            "SPN 597", "Brake Switch Status",
            lambda: sig.spn597_brake,
            lambda on: (setattr(sig, "spn597_brake", on), sig.notify()),
        )
        bool_toggle(
            "SPN 598", "Clutch Switch",
            lambda: sig.spn598_clutch,
            lambda on: (setattr(sig, "spn598_clutch", on), sig.notify()),
        )


def build_fuel(sig: SignalState, payload_labels: dict, containers: dict) -> None:
    card = ui.element("div").classes("pgn-card")
    containers["fuel"] = card
    with card:
        pgn_header(
            "FUEL",
            "Fuel Economy (Liquid)",
            "PGN 65266 (0x00FEF2)",
            "CAN ID: 0x18FEF200",
            sig.cycle_fuel_ms,
            lambda ms: (setattr(sig, "cycle_fuel_ms", ms), sig.notify()),
        )
        payload_labels["fuel"] = payload_strip(6, payload_hex(encode_fuel(sig)))
        slider_spn(
            "SPN 183", "Engine Fuel Rate", "gal/h", sig.spn183_fuel_rate_gal_h, 0, 40, 0.2,
            _bind(sig, "spn183_fuel_rate_gal_h"), decimals=1,
        )
        slider_spn(
            "SPN 184", "Instantaneous Fuel Economy", "mpg", sig.spn184_economy_mpg, 0, 20, 0.1,
            _bind(sig, "spn184_economy_mpg"), decimals=2,
        )
        slider_spn(
            "SPN 91", "Throttle Position", "%", sig.spn91_throttle_pct, 0, 100, 1,
            _bind(sig, "spn91_throttle_pct"),
        )


def build_et1(sig: SignalState, payload_labels: dict, containers: dict) -> None:
    card = ui.element("div").classes("pgn-card")
    containers["et1"] = card
    with card:
        pgn_header(
            "ET1",
            "Engine Temperature 1",
            "PGN 65262 (0x00FEEE)",
            "CAN ID: 0x18FEEE00",
            sig.cycle_et1_ms,
            lambda ms: (setattr(sig, "cycle_et1_ms", ms), sig.notify()),
        )
        payload_labels["et1"] = payload_strip(6, payload_hex(encode_et1(sig)))
        slider_spn(
            "SPN 110", "Engine Coolant Temperature", "°C", sig.spn110_coolant_c, -40, 125, 1,
            _bind(sig, "spn110_coolant_c"),
        )
        slider_spn(
            "SPN 175", "Engine Oil Temperature", "°C", sig.spn175_oil_c, -40, 150, 1,
            _bind(sig, "spn175_oil_c"),
        )
        slider_spn(
            "SPN 174", "Fuel Temperature", "°C", sig.spn174_fuel_c, -40, 120, 1,
            _bind(sig, "spn174_fuel_c"),
            presets=[("Ambient 20°C", 20), ("Nominal 45°C", 45), ("Hot 75°C", 75)],
        )


def build_vd(sig: SignalState, payload_labels: dict, containers: dict) -> None:
    card = ui.element("div").classes("pgn-card")
    containers["vd"] = card
    with card:
        pgn_header(
            "VD",
            "Vehicle Distance (Odometer)",
            "PGN 65248 (0x00FEE0)",
            "CAN ID: 0x18FEE000",
            sig.cycle_vd_ms,
            lambda ms: (setattr(sig, "cycle_vd_ms", ms), sig.notify()),
        )
        payload_labels["vd"] = payload_strip(6, payload_hex(encode_vd(sig)))
        slider_spn(
            "SPN 917", "Total Vehicle Distance", "mi", sig.spn917_total_mi, 0, 999999, 10,
            _bind(sig, "spn917_total_mi"), decimals=1, number_step=0.1,
        )
        slider_spn(
            "SPN 918", "Trip Distance", "mi", sig.spn918_trip_mi, 0, 10000, 1,
            _bind(sig, "spn918_trip_mi"), decimals=1, number_step=0.1,
        )


def build_ecu_pane(session, refs: dict[str, Any]) -> None:
    """ECU & Vehicle (VIN) tab matching standalone_v1.0.html."""
    identity = session.identity

    with ui.element("div").classes("card").style(
        "display:flex;flex-direction:column;gap:16px;"
    ):
        with ui.row().classes("w-full items-center justify-between").style(
            "border-bottom:1px solid #CBD5E1;padding-bottom:8px;"
        ):
            with ui.column().classes("gap-0"):
                ui.label("ECU & Vehicle Identity (Node 0x00)").style(
                    "font-size:14px;font-weight:700;text-transform:uppercase;"
                )
                ui.label(
                    "Engine Controller #1 · Primary Tractor Node (SAE J1939-81 Network Management)"
                ).classes("font-mono").style("font-size:11px;color:#5B6775;")
            claim_chip = ui.element("span").classes("status-pill stopped font-mono").style(
                "font-size:10px;"
            )
            with claim_chip:
                ui.element("span").classes("status-dot")
                claim_label = ui.label("NODE OFFLINE")
            refs["claim_chip"] = claim_chip
            refs["claim_label"] = claim_label

        with ui.element("div").style(
            "display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;"
        ):
            with ui.column().classes("gap-3"):
                with ui.element("div").style(
                    "background:#F8FAFC;border:1px solid #CBD5E1;border-radius:3px;"
                    "padding:16px;text-align:center;"
                ):
                    ui.html(
                        '<svg viewBox="0 0 320 100" style="width:100%;max-width:280px;height:80px;" '
                        'fill="none" stroke="#1F2A37" stroke-width="1.5">'
                        '<path d="M 45 80 L 45 50 L 55 35 L 95 20 L 155 18 L 210 20 L 245 28 L 270 50 '
                        'L 282 65 L 286 80 Z" fill="#E2E8F0" stroke="#1F6FEB"/>'
                        '<circle cx="80" cy="80" r="12" fill="#1F2A37"/>'
                        '<circle cx="250" cy="80" r="12" fill="#1F2A37"/>'
                        '<line x1="20" y1="92" x2="300" y2="92" stroke="#94A3B8" '
                        'stroke-dasharray="4 4"/></svg>',
                        sanitize=False,
                    )
                    ui.label("Class 8 Heavy Duty Tractor · Node 0x00").classes(
                        "font-mono"
                    ).style(
                        "margin-top:8px;font-size:11px;font-weight:700;color:#1F2A37;"
                    )

                with ui.element("div").style(
                    "background:#F8FAFC;border:1px solid #CBD5E1;border-radius:3px;padding:12px;"
                ):
                    ui.label("Vehicle Identification Number (VIN)").classes("field-label")
                    with ui.row().classes("w-full items-center gap-2").style("margin-top:4px;"):
                        vin_input = (
                            ui.input(value=identity.vin)
                            .props("dense outlined maxlength=17")
                            .classes("font-mono")
                            .style("flex:1;font-weight:700;text-transform:uppercase;")
                        )
                        btn_set_vin = ui.button("Set").classes(
                            "action-btn btn-start font-mono"
                        ).props("unelevated dense")
                        btn_copy = ui.button("Copy").classes(
                            "action-btn btn-restart font-mono"
                        ).props("unelevated dense")
                    ui.label(
                        "Broadcast on START and when Set (PGN 65260 / BAM). "
                        "Not Request/Response."
                    ).style("font-size:11px;color:#5B6775;margin-top:6px;")
                    refs["vin_input"] = vin_input

                    def on_vin_change(e=None) -> None:
                        raw = vin_input.value if e is None else getattr(e, "value", vin_input.value)
                        try:
                            cleaned = session.set_vin(str(raw or ""))
                            vin_input.value = cleaned
                            ui.notify(f"VIN set to {cleaned}", type="positive")
                        except ValueError as exc:
                            ui.notify(str(exc), type="negative")
                            vin_input.value = identity.vin

                    def on_copy() -> None:
                        text = str(vin_input.value or identity.vin)
                        try:
                            ui.clipboard.write(text)
                            ui.notify(f"VIN copied: {text}", type="info")
                        except Exception:
                            ui.notify(f"VIN: {text}", type="info")

                    btn_set_vin.on_click(lambda: on_vin_change())
                    btn_copy.on_click(on_copy)

            with ui.column().classes("gap-3"):
                with ui.element("div").style(
                    "background:#F8FAFC;border:1px solid #CBD5E1;border-radius:3px;padding:12px;"
                ):
                    ui.label("J1939-81 Network Address Parameters").style(
                        "font-weight:700;font-size:11px;text-transform:uppercase;"
                        "color:#1F2A37;margin-bottom:8px;"
                    )
                    with ui.element("div").classes("font-mono").style(
                        "display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:11px;"
                    ):
                        for label, value in (
                            ("Source Address (SA):", "0x00 (Engine #1)"),
                            ("Industry Group:", "0 (On-Highway)"),
                            ("Vehicle System:", "0 (Tractor)"),
                            ("Bitrate:", "500 kbit/s"),
                        ):
                            with ui.element("div").style(
                                "background:#FFF;padding:6px;border:1px solid #CBD5E1;"
                                "border-radius:3px;"
                            ):
                                ui.label(label).style(
                                    "color:#5B6775;font-size:10px;display:block;"
                                )
                                ui.label(value).style("font-weight:700;")
                    with ui.element("div").classes("font-mono").style(
                        "margin-top:8px;background:#FFF;padding:8px;"
                        "border:1px solid #CBD5E1;border-radius:3px;"
                    ):
                        ui.label("64-Bit Device NAME:").style(
                            "color:#5B6775;font-size:10px;display:block;"
                        )
                        ui.label(identity.name_hex).style(
                            "font-weight:700;color:#1F6FEB;"
                        )


def build_diagnostics_pane(session, refs: dict[str, Any]) -> None:
    """Diagnostics tab — 2 DTCs on DM1."""
    diag = session.diagnostics

    with ui.element("div").classes("card").style(
        "display:flex;flex-direction:column;gap:14px;"
    ):
        with ui.row().classes("w-full items-center justify-between").style(
            "border-bottom:1px solid #CBD5E1;padding-bottom:8px;"
        ):
            with ui.column().classes("gap-0"):
                ui.label("Diagnostics & Active Fault Codes (DM1)").style(
                    "font-size:14px;font-weight:700;text-transform:uppercase;"
                )
                ui.label(
                    "SAE J1939-73 Diagnostic Trouble Code (DTC) Fault Injection & Lamp Status"
                ).classes("font-mono").style("font-size:11px;color:#5B6775;")
            with ui.row().classes("gap-2"):
                btn_clear = ui.button("Clear All").classes(
                    "action-btn btn-restart font-mono"
                ).props("unelevated dense")
                btn_inject = ui.button("Inject Both").classes(
                    "action-btn btn-restart font-mono"
                ).props("unelevated dense")

        dm1_alert = ui.element("div").classes("font-mono").style(
            "display:none;background:#FFFBEB;border:1px solid #FDE68A;border-radius:3px;"
            "padding:10px;font-size:11px;color:#92400E;"
        )
        with dm1_alert:
            ui.label("PGN 65226 (DM1) Active Diagnostic Message Broadcast").style(
                "font-weight:700;"
            )
            ui.label(
                "CAN ID: 0x18FECA00 · Priority: 6 · Rate: 1000 ms. "
                "Telematics dashboards display MIL indicator."
            )
        refs["dm1_alert"] = dm1_alert

        with ui.element("div").classes("dtc-grid"):
            card1 = ui.element("div").classes("dtc-card")
            with card1:
                with ui.row().classes("w-full items-center justify-between").style(
                    "margin-bottom:8px;"
                ):
                    ui.label("SPN 110 / FMI 3").classes("badge-subtle font-mono").style(
                        "background:#FFFBEB;color:#B45309;border-color:#FDE68A;"
                    )
                    badge1 = ui.label("INACTIVE").classes("tab-pill font-mono")
                ui.label("Engine Coolant Temp Voltage High").style(
                    "font-weight:700;font-size:13px;color:#1F2A37;"
                )
                ui.label(
                    "Voltage Above Normal, Or Shorted To High Source. Amber Warning Lamp."
                ).style("font-size:11px;color:#5B6775;margin-top:4px;")
                with ui.row().classes("w-full items-center justify-between").style(
                    "border-top:1px solid #CBD5E1;padding-top:8px;"
                ):
                    ui.label("Lamp: Amber Warning").classes("font-mono").style(
                        "font-size:11px;color:#5B6775;"
                    )
                    btn1 = ui.button("Inject Fault").classes(
                        "action-btn btn-restart font-mono"
                    ).props("unelevated dense")

            card2 = ui.element("div").classes("dtc-card")
            with card2:
                with ui.row().classes("w-full items-center justify-between").style(
                    "margin-bottom:8px;"
                ):
                    ui.label("SPN 190 / FMI 0").classes("badge-subtle font-mono").style(
                        "background:#FEF2F2;color:#991B1B;border-color:#FCA5A5;"
                    )
                    badge2 = ui.label("INACTIVE").classes("tab-pill font-mono")
                ui.label("Engine Crankshaft Overspeed").style(
                    "font-weight:700;font-size:13px;color:#1F2A37;"
                )
                ui.label(
                    "Data Valid But Above Normal Operational Range - Most Severe Level. "
                    "Red Stop Lamp."
                ).style("font-size:11px;color:#5B6775;margin-top:4px;")
                with ui.row().classes("w-full items-center justify-between").style(
                    "border-top:1px solid #CBD5E1;padding-top:8px;"
                ):
                    ui.label("Lamp: Red Stop Lamp").classes("font-mono").style(
                        "font-size:11px;color:#5B6775;"
                    )
                    btn2 = ui.button("Inject Fault").classes(
                        "action-btn btn-restart font-mono"
                    ).props("unelevated dense")

        refs.update(
            {
                "dtc_card1": card1,
                "dtc_card2": card2,
                "dtc_badge1": badge1,
                "dtc_badge2": badge2,
                "dtc_btn1": btn1,
                "dtc_btn2": btn2,
            }
        )

        def refresh_dtc_ui() -> None:
            c = diag.active_count
            dm1_alert.style(
                "display:block;background:#FFFBEB;border:1px solid #FDE68A;"
                "border-radius:3px;padding:10px;font-size:11px;color:#92400E;"
                if c > 0
                else "display:none;"
            )
            if diag.dtc_spn110_fmi3:
                card1.classes(remove="fault-red", add="fault-amber")
                badge1.set_text("FAULT INJECTED")
                btn1.set_text("Clear Fault")
            else:
                card1.classes(remove="fault-amber fault-red")
                badge1.set_text("INACTIVE")
                btn1.set_text("Inject Fault")
            if diag.dtc_spn190_fmi0:
                card2.classes(remove="fault-amber", add="fault-red")
                badge2.set_text("FAULT INJECTED")
                btn2.set_text("Clear Fault")
            else:
                card2.classes(remove="fault-amber fault-red")
                badge2.set_text("INACTIVE")
                btn2.set_text("Inject Fault")
            pill = refs.get("diag_tab_pill")
            if pill is not None:
                if c > 0:
                    pill.set_text(f"{c} Active")
                    pill.classes(add="warn")
                else:
                    pill.set_text("2 Supported")
                    pill.classes(remove="warn")
            foot = refs.get("foot_dtc")
            if foot is not None:
                if c > 0:
                    foot.set_text(f"Active Faults: {c} DTCs")
                    foot.style("color:#B45309")
                else:
                    foot.set_text("Active Faults: 0 DTCs")
                    foot.style("color:#1F9D55")

        refs["refresh_dtc_ui"] = refresh_dtc_ui

        btn1.on_click(lambda: (session.set_dtc1(not diag.dtc_spn110_fmi3), refresh_dtc_ui()))
        btn2.on_click(lambda: (session.set_dtc2(not diag.dtc_spn190_fmi0), refresh_dtc_ui()))
        btn_clear.on_click(lambda: (session.clear_all_dtcs(), refresh_dtc_ui()))
        btn_inject.on_click(lambda: (session.inject_both_dtcs(), refresh_dtc_ui()))
        refresh_dtc_ui()
