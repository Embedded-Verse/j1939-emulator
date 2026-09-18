"""CLI entry: --gui | --config | --list-channels with runtime commands."""

from __future__ import annotations

import argparse
import sys
import warnings

from j1939_emulator import __version__
from j1939_emulator.bus.detect import (
    DetectedChannel,
    EmulationMode,
    detect_hardware,
    find_channel,
)
from j1939_emulator.bus.session import EmulatorSession
from j1939_emulator.config import load_config
from j1939_emulator.pgn import all_payloads


def _quiet_third_party_noise() -> None:
    """Hide known third-party warnings that scare end users at startup."""
    warnings.filterwarnings(
        "ignore",
        message=".*doesn't match a supported version.*",
        module="requests",
    )


def format_channel_table(
    channels: list[DetectedChannel],
    *,
    mode: EmulationMode | str,
    current_uid: str | None = None,
) -> str:
    """Simple channel list: use the number with --channel."""
    mode_s = mode.value if isinstance(mode, EmulationMode) else str(mode)
    title = "Virtual" if mode_s == "virtual" else "Real"
    lines = [f"Available {title} CAN channels ({len(channels)}):", ""]
    if not channels:
        lines.append("  (none found — plug in an adapter, or use --mode virtual)")
        return "\n".join(lines)

    lines.append("  #   Adapter")
    lines.append("  --  -----------------------------------------------")
    for i, ch in enumerate(channels, start=1):
        mark = " (current)" if current_uid and ch.uid == current_uid else ""
        lines.append(f"  {i:<3} {ch.label}{mark}")

    lines.append("")
    lines.append("Put the number after --channel. Example:")
    lines.append(
        f"  python -m j1939_emulator --config examples/ecu.toml "
        f"--mode {mode_s} --channel 1 --bitrate 500000"
    )
    lines.append("")
    lines.append("At the > prompt you can also type:  channels   or   channel 1")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="j1939_emulator",
        description="SAE J1939 Heavy-Duty Vehicle Emulator v1.0",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "--gui",
        action="store_true",
        help="Open NiceGUI in the browser (default http://127.0.0.1:8080)",
    )
    p.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="GUI bind host (default: 127.0.0.1)",
    )
    p.add_argument(
        "--port",
        type=int,
        default=8080,
        help="GUI HTTP port (default: 8080)",
    )
    p.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open the system browser in GUI mode",
    )
    p.add_argument(
        "--config",
        "-c",
        type=str,
        help="TOML ECU config (CLI mode)",
    )
    p.add_argument(
        "--mode",
        choices=["real", "virtual"],
        help="Override bus emulation mode",
    )
    p.add_argument(
        "--channel",
        type=str,
        help="Bus channel number from --list-channels (e.g. 1) or short name (e.g. vcan0)",
    )
    p.add_argument(
        "--bitrate",
        type=int,
        choices=[125000, 250000, 500000, 1000000],
        help="Override bitrate",
    )
    p.add_argument(
        "--list-channels",
        "-l",
        action="store_true",
        help="List detected channels for --mode (default: virtual) and exit",
    )
    p.add_argument(
        "--no-start",
        action="store_true",
        help="Do not auto-start emulation in CLI mode",
    )
    return p


_HELP_TEXT = """\
channels [real|virtual]  — list adapters; use the number with --channel / channel
channel [N]              — show current channel or select by number (e.g. channel 1)
mode [real|virtual]      — show or set emulation mode
bitrate [Hz]             — show or set bitrate (125000|250000|500000|1000000)
info                     — dump runtime config (script/cloud friendly)
status                   — uptime / TX / load / claim / DTCs
payloads                 — current PGN hex
get <key>                — read SPN (e.g. get eec1.spn190_rpm)
set <key> <value>        — change SPN (e.g. set eec1.spn190_rpm 2100)
vin [value]              — show or set 17-char VIN
dtc 1|2|both on|off      — inject/clear DM1 faults
stop | start | reset | help | quit"""


def main(argv: list[str] | None = None) -> int:
    _quiet_third_party_noise()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.gui:
        if not (1 <= int(args.port) <= 65535):
            print("error: --port must be between 1 and 65535", file=sys.stderr)
            return 2
        from j1939_emulator.gui.app import run_gui

        run_gui(
            config_path=args.config,
            host=args.host,
            port=int(args.port),
            open_browser=not args.no_browser,
        )
        return 0

    if args.list_channels:
        mode = EmulationMode(args.mode or "virtual")
        channels = detect_hardware(mode=mode, timeout=6.0)
        print(format_channel_table(channels, mode=mode))
        return 0

    if not args.config and not (args.mode or args.channel or args.bitrate):
        parser.print_help()
        print(
            "\nExamples:\n"
            "  python -m j1939_emulator --list-channels --mode virtual\n"
            "  python -m j1939_emulator --list-channels --mode real\n"
            "  python -m j1939_emulator --gui\n"
            "  python -m j1939_emulator --config examples/ecu.toml\n"
            "  python -m j1939_emulator --config examples/ecu.toml "
            "--mode real --channel 1 --bitrate 500000\n"
            "\nAt the > prompt: channels | channel 1 | mode | bitrate | info | "
            "get/set | vin | dtc | status | help\n",
            file=sys.stderr,
        )
        return 0

    return run_cli(args)


def run_cli(args: argparse.Namespace) -> int:
    if args.config:
        cfg = load_config(args.config)
        signals = cfg.signals
        identity = cfg.identity
        diagnostics = cfg.diagnostics
        mode = cfg.bus.mode
        channel_name = cfg.bus.channel
        bitrate = cfg.bus.bitrate
        start = cfg.start_on_launch and not args.no_start
    else:
        from j1939_emulator.diagnostics import DiagnosticState
        from j1939_emulator.ecu_identity import EcuIdentity
        from j1939_emulator.pgn import SignalState

        signals = SignalState()
        identity = EcuIdentity()
        diagnostics = DiagnosticState()
        mode = EmulationMode(args.mode or "virtual")
        channel_name = args.channel or "vcan0"
        bitrate = args.bitrate or 500_000
        start = not args.no_start

    if args.mode:
        mode = EmulationMode(args.mode)
    if args.channel:
        channel_name = args.channel
    if args.bitrate:
        bitrate = args.bitrate

    try:
        channel = find_channel(mode, channel_name)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(
            format_channel_table(detect_hardware(mode=mode, timeout=6.0), mode=mode),
            file=sys.stderr,
        )
        print(
            "\nList channels first:\n"
            f"  python -m j1939_emulator --list-channels --mode {mode.value}",
            file=sys.stderr,
        )
        return 2

    session = EmulatorSession(
        signals=signals,
        identity=identity,
        diagnostics=diagnostics,
        bitrate=bitrate,
        mode=mode,
    )
    print(
        f"j1939-emulator {__version__}  mode={mode.value} "
        f"channel={channel.label!r} bitrate={bitrate} vin={identity.vin}"
    )
    print(
        "Commands: channels | channel | mode | bitrate | info | "
        "get/set | vin | dtc | status | payloads | stop/start/reset | help | quit"
    )

    if start:
        try:
            session.start(channel, bitrate=bitrate)
            print("STARTED")
            print(
                f"claimed={session.address_claimed} "
                f"active_dtcs={session.diagnostics.active_count}"
            )
        except Exception as exc:
            print(f"error: failed to start: {exc}", file=sys.stderr)
            return 3

    try:
        while True:
            try:
                line = input("> ").strip()
            except EOFError:
                print()
                break
            if not line:
                continue
            parts = line.split(maxsplit=2)
            cmd = parts[0].lower()
            rest = parts[1:]

            if cmd in ("quit", "exit", "q"):
                break
            if cmd == "help":
                print(_HELP_TEXT)
                continue
            if cmd in ("channels", "ls", "list"):
                list_mode = mode
                if rest:
                    m = rest[0].lower()
                    if m not in ("real", "virtual"):
                        print("usage: channels [real|virtual]")
                        continue
                    list_mode = EmulationMode(m)
                chs = detect_hardware(mode=list_mode, timeout=6.0)
                print(
                    format_channel_table(
                        chs, mode=list_mode, current_uid=channel.uid
                    )
                )
                continue
            if cmd == "channel":
                if not rest:
                    print(f"channel={channel.label!r} mode={mode.value}")
                    continue
                needle = rest[0] if len(rest) == 1 else " ".join(rest)
                try:
                    new_ch = find_channel(mode, needle)
                except ValueError as exc:
                    print(f"error: {exc}")
                    print(
                        format_channel_table(
                            detect_hardware(mode=mode, timeout=6.0),
                            mode=mode,
                            current_uid=channel.uid,
                        )
                    )
                    continue
                was_running = session.running
                if was_running:
                    session.stop()
                    print("STOPPED")
                channel = new_ch
                channel_name = new_ch.uid
                print(f"ok channel={channel.label!r}")
                if was_running:
                    try:
                        session.start(channel, bitrate=bitrate)
                        print("STARTED")
                    except Exception as exc:
                        print(f"error: {exc}")
                continue
            if cmd == "mode":
                if not rest:
                    print(f"mode={mode.value}")
                    continue
                m = rest[0].lower()
                if m not in ("real", "virtual"):
                    print("usage: mode real|virtual")
                    continue
                new_mode = EmulationMode(m)
                if new_mode is mode:
                    print(f"mode={mode.value}")
                    continue
                was_running = session.running
                if was_running:
                    session.stop()
                    print("STOPPED")
                mode = new_mode
                session.mode = mode
                # Pick a sensible default channel for the new mode
                chs = detect_hardware(mode=mode, timeout=6.0)
                if not chs:
                    print(f"ok mode={mode.value} (no channels — run: channels)")
                    continue
                channel = chs[0]
                channel_name = channel.uid
                print(f"ok mode={mode.value} channel={channel.label!r}")
                print(format_channel_table(chs, mode=mode, current_uid=channel.uid))
                if was_running:
                    try:
                        session.start(channel, bitrate=bitrate)
                        print("STARTED")
                    except Exception as exc:
                        print(f"error: {exc}")
                continue
            if cmd == "bitrate":
                if not rest:
                    print(f"bitrate={bitrate}")
                    continue
                try:
                    br = int(rest[0])
                except ValueError:
                    print("usage: bitrate 125000|250000|500000|1000000")
                    continue
                if br not in (125_000, 250_000, 500_000, 1_000_000):
                    print("error: bitrate must be 125000|250000|500000|1000000")
                    continue
                bitrate = br
                session.bitrate = br
                print(f"ok bitrate={bitrate} (applies on next start/reset if stopped)")
                if session.running:
                    try:
                        session.reset(channel, bitrate=bitrate)
                        print("RESET")
                    except Exception as exc:
                        print(f"error: {exc}")
                continue
            if cmd == "info":
                st = session.stats()
                print(
                    f"version={__version__}\n"
                    f"mode={mode.value}\n"
                    f"channel={channel.label}\n"
                    f"bitrate={bitrate}\n"
                    f"running={st.running}\n"
                    f"claimed={st.address_claimed}\n"
                    f"sa=0x{st.sa:02X}\n"
                    f"vin={session.identity.vin}\n"
                    f"dtc1={session.diagnostics.dtc_spn110_fmi3}\n"
                    f"dtc2={session.diagnostics.dtc_spn190_fmi0}\n"
                    f"tx={st.tx_count}\n"
                    f"load_pct={st.load_pct:.1f}"
                )
                continue
            if cmd == "status":
                st = session.stats()
                mm = int(st.uptime_s) // 60
                ss = int(st.uptime_s) % 60
                print(
                    f"running={st.running} claimed={st.address_claimed} "
                    f"uptime={mm:02d}:{ss:02d} tx={st.tx_count} "
                    f"load={st.load_pct:.1f}% bitrate={st.bitrate} "
                    f"dtcs={st.active_dtcs} vin={session.identity.vin} "
                    f"channel={channel.label!r}"
                )
                continue
            if cmd == "payloads":
                for name, hex_s in all_payloads(session.signals).items():
                    print(f"{name}: {hex_s}")
                continue
            if cmd == "get":
                if not rest:
                    print("usage: get <key>")
                    continue
                try:
                    print(f"{rest[0]}={session.signals.get_spn(rest[0])}")
                except KeyError as exc:
                    print(f"error: {exc}")
                continue
            if cmd == "vin":
                if not rest:
                    print(f"vin={session.identity.vin}")
                    continue
                try:
                    cleaned = session.set_vin(
                        rest[0] if len(rest) == 1 else " ".join(rest)
                    )
                    print(f"ok vin={cleaned}")
                except ValueError as exc:
                    print(f"error: {exc}")
                continue
            if cmd == "dtc":
                if len(rest) < 2:
                    print(
                        "usage: dtc <1|2|both> <on|off>\n"
                        f"active: dtc1={session.diagnostics.dtc_spn110_fmi3} "
                        f"dtc2={session.diagnostics.dtc_spn190_fmi0}"
                    )
                    continue
                which, state_s = rest[0].lower(), rest[1].lower()
                active = state_s in ("on", "1", "true", "inject")
                if state_s in ("off", "0", "false", "clear"):
                    active = False
                elif state_s not in ("on", "1", "true", "inject"):
                    print("error: state must be on|off")
                    continue
                if which in ("1", "dtc1", "110"):
                    session.set_dtc1(active)
                elif which in ("2", "dtc2", "190"):
                    session.set_dtc2(active)
                elif which == "both":
                    if active:
                        session.inject_both_dtcs()
                    else:
                        session.clear_all_dtcs()
                else:
                    print("error: which must be 1|2|both")
                    continue
                print(
                    f"ok dtc1={session.diagnostics.dtc_spn110_fmi3} "
                    f"dtc2={session.diagnostics.dtc_spn190_fmi0}"
                )
                continue
            if cmd == "stop":
                session.stop()
                print("STOPPED")
                continue
            if cmd == "start":
                try:
                    session.start(channel, bitrate=bitrate)
                    print("STARTED")
                except Exception as exc:
                    print(f"error: {exc}")
                continue
            if cmd == "reset":
                try:
                    session.reset(channel, bitrate=bitrate)
                    print("RESET")
                except Exception as exc:
                    print(f"error: {exc}")
                continue
            if cmd == "set":
                if len(rest) < 2:
                    print("usage: set <key> <value>")
                    continue
                key, value = rest[0], rest[1]
                try:
                    session.signals.set_spn(key, value)
                    print(f"ok {key}={value}")
                except (KeyError, ValueError) as exc:
                    print(f"error: {exc}")
                continue
            print(f"unknown command: {cmd}  (type help)")
    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        session.stop()
        print("Bus closed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
