from pathlib import Path
import textwrap, zipfile, os

root = Path("/mnt/data/HCDM1_Virtual_Test_Bench")
(root / "Common").mkdir(parents=True, exist_ok=True)
(root / "Simulation").mkdir(parents=True, exist_ok=True)
(root / "Tests").mkdir(parents=True, exist_ok=True)

files = {}

files["Common/__init__.py"] = ""
files["Simulation/__init__.py"] = ""

files["Common/protocol.py"] = r'''
"""HCDM-1 logical IR packet protocol.

This module is hardware-independent and can be imported by desktop Python
or MicroPython (the simulator itself uses desktop-only Tkinter).
"""
PACKET_LENGTH = 16
DATA_LENGTH = 14
CRC_INIT = 0xFFFF
CRC_POLY = 0x1021


def crc16_ccitt(data, initial=CRC_INIT):
    crc = initial
    for byte in data:
        crc ^= (byte & 0xFF) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ CRC_POLY) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def encode_packet(rgb_groups, motor, sequence):
    """Create a 16-byte packet from four RGB tuples, motor bool, and sequence."""
    if len(rgb_groups) != 4:
        raise ValueError("Exactly four RGB groups are required")
    payload = bytearray()
    for group in rgb_groups:
        if len(group) != 3:
            raise ValueError("Each RGB group must contain R, G, B")
        for value in group:
            value = int(value)
            if not 0 <= value <= 255:
                raise ValueError("RGB values must be in range 0..255")
            payload.append(value)
    payload.append(1 if motor else 0)
    payload.append(int(sequence) & 0xFF)
    crc = crc16_ccitt(payload)
    payload.extend(((crc >> 8) & 0xFF, crc & 0xFF))
    return bytes(payload)


def decode_packet(packet):
    """Validate and decode a packet. Raises ValueError for malformed/invalid data."""
    packet = bytes(packet)
    if len(packet) != PACKET_LENGTH:
        raise ValueError("Incorrect packet length")
    expected = crc16_ccitt(packet[:DATA_LENGTH])
    received = (packet[14] << 8) | packet[15]
    if expected != received:
        raise ValueError("CRC mismatch")
    groups = []
    for i in range(0, 12, 3):
        groups.append(tuple(packet[i:i + 3]))
    return {
        "rgb_groups": groups,
        "motor": bool(packet[12] & 0x01),
        "sequence": packet[13],
    }


def packet_to_symbols(packet):
    """Return 64 two-bit symbols, most-significant pair first."""
    packet = bytes(packet)
    if len(packet) != PACKET_LENGTH:
        raise ValueError("Incorrect packet length")
    symbols = []
    for byte in packet:
        for shift in (6, 4, 2, 0):
            symbols.append((byte >> shift) & 0x03)
    return symbols


def symbols_to_burst_groups(packet):
    """Logical burst-group representation: sync group of 8, then 1..4 bursts."""
    return [8] + [symbol + 1 for symbol in packet_to_symbols(packet)]


def packet_hex(packet):
    return " ".join("{:02X}".format(b) for b in packet)
'''

files["Common/dmx.py"] = r'''
"""Small DMX channel mapping helper for the HCDM-1 13-channel personality."""
PERSONALITY_CHANNELS = 13
UNIVERSE_SIZE = 512


def address_from_dips(dips):
    """DIP 1..9 are booleans; True means ON. DIP 1 is the LSB."""
    if len(dips) != 9:
        raise ValueError("Provide DIP 1 through DIP 9")
    return sum((1 << index) for index, enabled in enumerate(dips) if enabled)


def valid_start_address(address):
    return 1 <= int(address) <= (UNIVERSE_SIZE - PERSONALITY_CHANNELS + 1)


def decode_personality(universe, start_address):
    """Decode 13 consecutive DMX slots, using a 1-based start address."""
    if len(universe) < UNIVERSE_SIZE:
        raise ValueError("DMX universe must contain 512 slots")
    if not valid_start_address(start_address):
        raise ValueError("Start address must be between 1 and 500")
    start = start_address - 1
    values = [int(v) & 0xFF for v in universe[start:start + PERSONALITY_CHANNELS]]
    groups = [
        tuple(values[0:3]),
        tuple(values[3:6]),
        tuple(values[6:9]),
        tuple(values[9:12]),
    ]
    return groups, values[12] >= 128
'''

files["Simulation/simulator.py"] = r'''
"""HCDM-1 Virtual Test Bench - desktop-only Tkinter simulation."""
import random
import sys
import time
import tkinter as tk
from tkinter import ttk, messagebox

from Common.dmx import address_from_dips, decode_personality, valid_start_address
from Common.protocol import encode_packet, decode_packet, packet_hex, symbols_to_burst_groups

PACKET_INTERVAL_MS = 1500
DMX_TIMEOUT_MS = 1000
PROP_SIGNAL_TIMEOUT_MS = 15000
TICK_MS = 100


class VirtualProp:
    def __init__(self, number):
        self.number = number
        self.mode_b = False
        self.link_blocked = False
        self.corruption_percent = 0
        self.sensors_enabled = [True] * 4
        self.logical_rgb = [(0, 0, 255)] * 4
        self.motor_on = False
        self.last_valid_ms = None
        self.last_sequence = None
        self.last_sequence_ms = -10_000
        self.timeout_active = True
        self.accepted = 0
        self.rejected = 0
        self.lost = 0
        self.sensor_hits = 0

    def receive(self, packet, now_ms, rng):
        if self.link_blocked:
            self.lost += 1
            return "LINK BLOCKED"
        enabled_count = sum(self.sensors_enabled)
        if enabled_count == 0:
            self.lost += 1
            return "NO SENSORS"
        # One complete frame can be received by any enabled redundant sensor.
        # The sensor hit is chosen only to make redundancy visible in the UI.
        sensor_index = rng.choice([i for i, enabled in enumerate(self.sensors_enabled) if enabled])
        self.sensor_hits += 1
        candidate = bytearray(packet)
        if rng.random() < (self.corruption_percent / 100.0):
            candidate[rng.randrange(0, 14)] ^= 1 << rng.randrange(0, 8)
        try:
            decoded = decode_packet(candidate)
        except ValueError:
            self.rejected += 1
            return "CRC REJECT (S{})".format(sensor_index + 1)
        if decoded["sequence"] == self.last_sequence and (now_ms - self.last_sequence_ms) < 5000:
            return "DUPLICATE"
        self.logical_rgb = decoded["rgb_groups"]
        self.motor_on = decoded["motor"]
        self.last_sequence = decoded["sequence"]
        self.last_sequence_ms = now_ms
        self.last_valid_ms = now_ms
        self.timeout_active = False
        self.accepted += 1
        return "ACCEPTED (S{})".format(sensor_index + 1)

    def update_timeout(self, now_ms):
        if self.last_valid_ms is None or now_ms - self.last_valid_ms >= PROP_SIGNAL_TIMEOUT_MS:
            self.logical_rgb = [(0, 0, 255)] * 4
            self.motor_on = False
            self.timeout_active = True

    def displayed_rgb(self):
        return list(reversed(self.logical_rgb)) if self.mode_b else list(self.logical_rgb)


class HCDM1Simulator:
    def __init__(self, root):
        self.root = root
        self.root.title("HCDM-1 Virtual Test Bench")
        self.root.geometry("1420x940")
        self.root.minsize(1100, 760)
        self.rng = random.Random()
        self.now_ms = 0
        self.sequence = 0
        self.last_tx_ms = -PACKET_INTERVAL_MS
        self.auto_running = False
        self.dmx_present = True
        self.last_dmx_ms = 0
        self.ir_enabled = True
        self.dips = [False] * 9
        self.dmx = [0] * 512
        self.props = [VirtualProp(i + 1) for i in range(4)]
        self.prop_widgets = []
        self._build_ui()
        self._refresh_all()
        self._log("Simulator ready. This is a logical/software model, not an electrical or optical validation.")

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(self.root, padding=8)
        toolbar.grid(row=0, column=0, sticky="ew")
        self.clock_var = tk.StringVar(value="Virtual time: 0.0 s")
        ttk.Label(toolbar, textvariable=self.clock_var, font=("Segoe UI", 11, "bold")).pack(side="left", padx=(0, 18))
        self.run_btn = ttk.Button(toolbar, text="Start simulation", command=self.toggle_run)
        self.run_btn.pack(side="left", padx=3)
        ttk.Button(toolbar, text="Advance 100 ms", command=lambda: self.advance(100)).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Advance 1 s", command=lambda: self.advance(1000)).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Advance 15 s", command=lambda: self.advance(15000)).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Send IR now", command=self.transmit).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Reset simulation", command=self.reset).pack(side="left", padx=3)

        main = ttk.Panedwindow(self.root, orient="horizontal")
        main.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        left = ttk.Frame(main, padding=6)
        right = ttk.Frame(main, padding=6)
        main.add(left, weight=1)
        main.add(right, weight=2)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(3, weight=1)

        tx = ttk.LabelFrame(left, text="Transmitter / DMX source", padding=8)
        tx.grid(row=0, column=0, sticky="ew", pady=4)
        tx.columnconfigure(1, weight=1)
        self.address_var = tk.StringVar()
        self.address_status = tk.StringVar()
        ttk.Label(tx, text="DIP 1–9 address (binary)").grid(row=0, column=0, sticky="w")
        dip_frame = ttk.Frame(tx)
        dip_frame.grid(row=1, column=0, columnspan=2, sticky="w", pady=4)
        for i in range(9):
            var = tk.BooleanVar(value=False)
            self.dips[i] = var
            cb = ttk.Checkbutton(dip_frame, text=str(i + 1), variable=var, command=self._refresh_address)
            cb.grid(row=0, column=i, padx=3)
        self.ir_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(tx, text="DIP 10: IR transmit enabled", variable=self.ir_var,
                        command=self._refresh_all).grid(row=2, column=0, columnspan=2, sticky="w")
        self.dmx_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(tx, text="DMX signal present", variable=self.dmx_var,
                        command=self._dmx_presence_changed).grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Label(tx, textvariable=self.address_var).grid(row=4, column=0, sticky="w", pady=(5, 0))
        ttk.Label(tx, textvariable=self.address_status).grid(row=4, column=1, sticky="e", pady=(5, 0))

        controls = ttk.LabelFrame(left, text="DMX personality controls", padding=8)
        controls.grid(row=1, column=0, sticky="ew", pady=4)
        controls.columnconfigure(1, weight=1)
        self.channel_vars = []
        channel_names = [
            "Group 1 Red", "Group 1 Green", "Group 1 Blue",
            "Group 2 Red", "Group 2 Green", "Group 2 Blue",
            "Group 3 Red", "Group 3 Green", "Group 3 Blue",
            "Group 4 Red", "Group 4 Green", "Group 4 Blue",
            "Motor (0–255; ON >=128)",
        ]
        for idx, name in enumerate(channel_names):
            var = tk.IntVar(value=0)
            self.channel_vars.append(var)
            ttk.Label(controls, text=name, width=25).grid(row=idx, column=0, sticky="w")
            scale = ttk.Scale(controls, from_=0, to=255, orient="horizontal",
                              command=lambda value, i=idx: self._slider_changed(i, value))
            scale.set(0)
            scale.grid(row=idx, column=1, sticky="ew", padx=5)
            value_label = ttk.Label(controls, textvariable=tk.StringVar(value="0"), width=4)
            value_label.grid(row=idx, column=2)
            self.channel_value_labels.append(value_label) if hasattr(self, "channel_value_labels") else None
            if not hasattr(self, "channel_value_labels"):
                self.channel_value_labels = [value_label]
            else:
                self.channel_value_labels.append(value_label)
            self.dmx_scales = getattr(self, "dmx_scales", [])
            self.dmx_scales.append(scale)
        self._refresh_address()

        info = ttk.LabelFrame(left, text="Protocol / model assumptions", padding=8)
        info.grid(row=2, column=0, sticky="ew", pady=4)
        info_text = (
            "Packet: 16 bytes | CRC-16/CCITT\n"
            "IR carrier model: 38 kHz | burst: 600 µs\n"
            "Packet interval: 1,500 ms | prop timeout: 15 s\n"
            "DMX stale threshold: 1 s; motor forced OFF\n"
            "Four 2-bit RGB groups + motor + sequence + CRC"
        )
        ttk.Label(info, text=info_text, justify="left").pack(anchor="w")

        props_frame = ttk.Frame(right)
        props_frame.pack(fill="both", expand=True)
        for i, prop in enumerate(self.props):
            card = ttk.LabelFrame(props_frame, text="Virtual Prop {}".format(prop.number), padding=8)
            card.grid(row=i // 2, column=i % 2, sticky="nsew", padx=5, pady=5)
            props_frame.columnconfigure(i % 2, weight=1)
            props_frame.rowconfigure(i // 2, weight=1)
            self._build_prop_card(card, prop)

        log_frame = ttk.LabelFrame(right, text="Event log / packet diagnostics", padding=6)
        log_frame.pack(fill="both", expand=False, pady=(8, 0))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=10, wrap="word", state="disabled", font=("Consolas", 9))
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)

    def _build_prop_card(self, parent, prop):
        frame = {}
        frame["mode"] = tk.BooleanVar(value=False)
        frame["blocked"] = tk.BooleanVar(value=False)
        frame["corrupt"] = tk.IntVar(value=0)
        ttk.Checkbutton(parent, text="Mode B (reverse LED group mapping)", variable=frame["mode"],
                        command=lambda p=prop, f=frame: self._prop_changed(p, f)).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(parent, text="Block IR link", variable=frame["blocked"],
                        command=lambda p=prop, f=frame: self._prop_changed(p, f)).grid(row=1, column=0, sticky="w")
        ttk.Label(parent, text="Corruption probability").grid(row=2, column=0, sticky="w")
        ttk.Spinbox(parent, from_=0, to=100, width=5, textvariable=frame["corrupt"],
                    command=lambda p=prop, f=frame: self._prop_changed(p, f)).grid(row=2, column=1, sticky="e")
        sensor_vars = []
        sensor_row = ttk.Frame(parent)
        sensor_row.grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Label(sensor_row, text="IR sensors:").pack(side="left")
        for j in range(4):
            v = tk.BooleanVar(value=True)
            sensor_vars.append(v)
            ttk.Checkbutton(sensor_row, text=str(j + 1), variable=v,
                            command=lambda p=prop, f=frame: self._prop_changed(p, f)).pack(side="left")
        frame["sensors"] = sensor_vars
        status = tk.StringVar(value="Waiting for first valid packet")
        frame["status"] = status
        ttk.Label(parent, textvariable=status, wraplength=300).grid(row=4, column=0, columnspan=2, sticky="w", pady=3)
        led_frame = ttk.Frame(parent)
        led_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=4)
        led_swatches = []
        for j in range(4):
            swatch = tk.Label(led_frame, text="G{}".format(j + 1), width=8, relief="groove", bg="#0000ff", fg="white")
            swatch.pack(side="left", padx=2, expand=True, fill="x")
            led_swatches.append(swatch)
        frame["swatches"] = led_swatches
        motor = tk.StringVar(value="Motor: OFF")
        frame["motor"] = motor
        ttk.Label(parent, textvariable=motor).grid(row=6, column=0, sticky="w")
        stats = tk.StringVar(value="RX 0 | CRC reject 0 | lost 0")
        frame["stats"] = stats
        ttk.Label(parent, textvariable=stats).grid(row=7, column=0, columnspan=2, sticky="w")
        self.prop_widgets.append(frame)

    def _prop_changed(self, prop, frame):
        prop.mode_b = frame["mode"].get()
        prop.link_blocked = frame["blocked"].get()
        prop.corruption_percent = max(0, min(100, int(frame["corrupt"].get())))
        prop.sensors_enabled = [v.get() for v in frame["sensors"]]
        self._refresh_prop(prop)

    def _refresh_address(self):
        dips = [v.get() for v in self.dips]
        address = address_from_dips(dips)
        self.address_var.set("DMX start address: {}".format(address))
        self.address_status.set("VALID" if valid_start_address(address) else "INVALID (use 1–500)")
        self._refresh_all()

    def _slider_changed(self, index, value):
        n = int(float(value))
        self.channel_vars[index].set(n)
        self.channel_value_labels[index].configure(text=str(n))
        self._update_dmx_from_controls()

    def _update_dmx_from_controls(self):
        address = address_from_dips([v.get() for v in self.dips])
        if not valid_start_address(address):
            return
        for i, var in enumerate(self.channel_vars):
            self.dmx[address - 1 + i] = var.get()
        self.last_dmx_ms = self.now_ms

    def _dmx_presence_changed(self):
        self.dmx_present = self.dmx_var.get()
        if self.dmx_present:
            self.last_dmx_ms = self.now_ms
        self._refresh_all()

    def _get_current_values(self):
        address = address_from_dips([v.get() for v in self.dips])
        if not valid_start_address(address):
            return [(0, 0, 0)] * 4, False, False
        groups, motor = decode_personality(self.dmx, address)
        dmx_fresh = self.dmx_present and (self.now_ms - self.last_dmx_ms <= DMX_TIMEOUT_MS)
        if not dmx_fresh:
            motor = False
        return groups, motor, dmx_fresh

    def transmit(self):
        if not self.ir_var.get():
            self._log("TX skipped: DIP 10 / IR enable is OFF.")
            return
        groups, motor, dmx_fresh = self._get_current_values()
        packet = encode_packet(groups, motor, self.sequence)
        burst_groups = symbols_to_burst_groups(packet)
        self._log("TX seq={} addr={} DMX={} motor={} packet={}".format(
            self.sequence, address_from_dips([v.get() for v in self.dips]),
            "FRESH" if dmx_fresh else "STALE", "ON" if motor else "OFF", packet_hex(packet)))
        self._log("IR logical frame: {} burst groups (sync + 64 symbols); modeled 38 kHz carrier.".format(len(burst_groups)))
        for prop in self.props:
            result = prop.receive(packet, self.now_ms, self.rng)
            self._log("  Prop {}: {}".format(prop.number, result))
            self._refresh_prop(prop)
        self.sequence = (self.sequence + 1) & 0xFF
        self.last_tx_ms = self.now_ms

    def advance(self, milliseconds):
        target = self.now_ms + milliseconds
        while self.now_ms < target:
            self.now_ms = min(target, self.now_ms + TICK_MS)
            if self.ir_var.get() and self.now_ms - self.last_tx_ms >= PACKET_INTERVAL_MS:
                self.transmit()
            for prop in self.props:
                was_timeout = prop.timeout_active
                prop.update_timeout(self.now_ms)
                if prop.timeout_active and not was_timeout:
                    self._log("Prop {} entered 15-second signal-loss fallback: blue / motor OFF.".format(prop.number))
                self._refresh_prop(prop)
        self._refresh_clock()

    def toggle_run(self):
        self.auto_running = not self.auto_running
        self.run_btn.configure(text="Pause simulation" if self.auto_running else "Start simulation")
        if self.auto_running:
            self._auto_tick()

    def _auto_tick(self):
        if not self.auto_running:
            return
        self.advance(TICK_MS)
        self.root.after(TICK_MS, self._auto_tick)

    def reset(self):
        self.auto_running = False
        self.run_btn.configure(text="Start simulation")
        self.now_ms = 0
        self.sequence = 0
        self.last_tx_ms = -PACKET_INTERVAL_MS
        self.last_dmx_ms = 0
        self.dmx = [0] * 512
        for i, var in enumerate(self.channel_vars):
            var.set(0)
            self.dmx_scales[i].set(0)
            self.channel_value_labels[i].configure(text="0")
        for prop in self.props:
            fresh = VirtualProp(prop.number)
            prop.__dict__.update(fresh.__dict__)
        for frame in self.prop_widgets:
            frame["mode"].set(False)
            frame["blocked"].set(False)
            frame["corrupt"].set(0)
            for sensor in frame["sensors"]:
                sensor.set(True)
        self._clear_log()
        self._log("Simulation reset.")
        self._refresh_all()

    def _refresh_prop(self, prop):
        frame = self.prop_widgets[prop.number - 1]
        colors = prop.displayed_rgb()
        for swatch, rgb in zip(frame["swatches"], colors):
            color = "#{:02x}{:02x}{:02x}".format(*rgb)
            swatch.configure(bg=color, fg="white" if sum(rgb) < 380 else "black")
        frame["motor"].set("Motor: {}".format("ON" if prop.motor_on else "OFF"))
        if prop.timeout_active:
            frame["status"].set("TIMEOUT FALLBACK — blue; waiting for valid frame")
        elif prop.link_blocked:
            frame["status"].set("Link blocked (last valid state held until timeout)")
        else:
            frame["status"].set("Receiving; last valid at {:.1f} s".format((prop.last_valid_ms or 0) / 1000))
        frame["stats"].set("RX {} | CRC reject {} | lost {} | sensor hits {}".format(
            prop.accepted, prop.rejected, prop.lost, prop.sensor_hits))

    def _refresh_all(self):
        self.ir_enabled = self.ir_var.get()
        for prop in self.props:
            self._refresh_prop(prop)
        self._refresh_clock()

    def _refresh_clock(self):
        self.clock_var.set("Virtual time: {:.1f} s".format(self.now_ms / 1000))

    def _log(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", "[{:8.1f}s] {}\n".format(self.now_ms / 1000, message))
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")


def main():
    root = tk.Tk()
    HCDM1Simulator(root)
    root.mainloop()


if __name__ == "__main__":
    main()
'''

files["Tests/test_protocol.py"] = r'''
import unittest
from Common.protocol import crc16_ccitt, encode_packet, decode_packet, packet_to_symbols


class ProtocolTests(unittest.TestCase):
    def test_crc_known_vector(self):
        self.assertEqual(crc16_ccitt(b"123456789"), 0x29B1)

    def test_round_trip(self):
        groups = [(1, 2, 3), (40, 50, 60), (100, 110, 120), (200, 210, 220)]
        packet = encode_packet(groups, True, 77)
        decoded = decode_packet(packet)
        self.assertEqual(decoded["rgb_groups"], groups)
        self.assertTrue(decoded["motor"])
        self.assertEqual(decoded["sequence"], 77)
        self.assertEqual(len(packet), 16)
        self.assertEqual(len(packet_to_symbols(packet)), 64)

    def test_corruption_rejected(self):
        packet = bytearray(encode_packet([(0, 0, 0)] * 4, False, 1))
        packet[3] ^= 0x01
        with self.assertRaises(ValueError):
            decode_packet(packet)


if __name__ == "__main__":
    unittest.main()
'''

files["Tests/test_dmx.py"] = r'''
import unittest
from Common.dmx import address_from_dips, valid_start_address, decode_personality


class DMXTests(unittest.TestCase):
    def test_dip_binary_address(self):
        dips = [True, False, True, False, False, True, True, False, False]
        self.assertEqual(address_from_dips(dips), 101)

    def test_valid_address_range(self):
        self.assertTrue(valid_start_address(1))
        self.assertTrue(valid_start_address(500))
        self.assertFalse(valid_start_address(0))
        self.assertFalse(valid_start_address(501))

    def test_personality_decode(self):
        universe = [0] * 512
        universe[99:112] = list(range(13))
        groups, motor = decode_personality(universe, 100)
        self.assertEqual(groups, [(0, 1, 2), (3, 4, 5), (6, 7, 8), (9, 10, 11)])
        self.assertFalse(motor)


if __name__ == "__main__":
    unittest.main()
'''

files["README.md"] = r'''
# HCDM-1 Virtual Test Bench

A desktop-only simulation environment for exercising the **logical behavior** of the HCDM-1 transmitter and four receiver props before hardware is available.

## Requirements

- Windows, macOS, or Linux
- Python 3.10 or newer
- Tkinter (normally included with the standard Python installer)
- No third-party Python packages are required

## Open in PyCharm

1. Extract `HCDM1_Virtual_Test_Bench.zip`.
2. In PyCharm, choose **Open** and select the extracted `HCDM1_Virtual_Test_Bench` folder.
3. Open `Simulation/simulator.py`.
4. Select your desktop Python interpreter (not a MicroPython interpreter).
5. Run `simulator.py` using the green Run button.

If Tkinter is missing on Linux, install your distribution's `python3-tk` package.

## Run automated tests

Open PyCharm's Terminal at the project root and run:

```bash
python -m unittest discover -s Tests -v
```

On Windows you can also double-click `run_tests.bat`.

## Simulator controls

- **DIP 1–9**: binary DMX start address, DIP 1 is the least significant bit.
- **DIP 10**: enables/disables IR transmission.
- **DMX signal present**: when disabled, DMX is treated as stale. After the 1-second stale threshold, RGB holds its last values and motor is forced OFF in transmitted data.
- **13 DMX controls**: four RGB groups (12 channels) and motor (channel 13; ON at 128 or above).
- **Mode B**: reverses the four logical RGB groups on that prop.
- **Block IR link**: simulates an obstructed or unavailable optical link.
- **Corruption probability**: randomly damages a packet before CRC validation.
- **Sensors 1–4**: independently disable redundant receiver modules. Any enabled sensor can receive a complete frame.
- **Advance buttons**: deterministic virtual-time testing, including the 15-second signal-loss fallback.
- **Send IR now**: sends one packet immediately.
- **Start simulation**: advances virtual time automatically.

## Implemented logical model

- 16-byte packet: 12 RGB bytes, motor byte, sequence byte, CRC-16/CCITT.
- CRC-16/CCITT-FALSE style parameters: initial `0xFFFF`, polynomial `0x1021`, no reflection, no final XOR.
- 64 two-bit symbols; logical burst-group list contains one 8-burst sync group plus 64 data-symbol groups of 1–4 bursts.
- 1,500 ms nominal packet interval.
- Four independent virtual props, each with four redundant virtual IR sensors.
- Duplicate sequence suppression (same sequence within five seconds).
- Receiver holds last valid state until 15 seconds after last valid packet, then falls back to blue on all groups and motor OFF.
- Mode A normal mapping; Mode B reverse group order.

## Important limitations

This simulator is **not** a hardware emulator and does not establish that the proposed optical link or electronics will work.

It does not model or validate:
- Actual 38 kHz PWM timing, emitter current, optical beam pattern, distance, or ambient-light immunity.
- TSSP77038 analog/demodulator pulse behavior, receiver recovery time, or sensor-to-sensor timing.
- The proposed burst protocol's decodability on the selected physical receiver.
- DMX electrical signaling, RS-485 transceiver behavior, break/MAB timing, or UART IRQ behavior.
- WS2812B timing, 3.3 V logic margin, level shifting, LED power integrity, or LED current.
- Motor driver electrical ratings, motor inrush, or mechanical behavior.
- MicroPython scheduling latency, memory pressure, or real-time performance on RP2040/RP2350.
- Power-loss behavior, eMMC/SDIO writes, or physical reliability.

The 600 µs burst, 1,900 µs symbol spacing, 6,000 µs group gap, 38 kHz carrier, and 1.5-second packet interval are represented as design assumptions, not measured hardware results. In particular, the TSSP77038 decoding scheme still requires bench validation with a logic analyzer before committing to PCB fabrication.

## Project layout

```text
HCDM1_Virtual_Test_Bench/
├── Common/
│   ├── __init__.py
│   ├── dmx.py
│   └── protocol.py
├── Simulation/
│   ├── __init__.py
│   └── simulator.py
├── Tests/
│   ├── test_dmx.py
│   └── test_protocol.py
├── README.md
├── requirements.txt
├── run_simulator.bat
└── run_tests.bat
```
'''

files["requirements.txt"] = "# Standard library only; no pip packages required.\n"
files["run_simulator.bat"] = r'''@echo off
cd /d "%~dp0"
python Simulation\simulator.py
pause
'''
files["run_tests.bat"] = r'''@echo off
cd /d "%~dp0"
python -m unittest discover -s Tests -v
pause
'''

# Write project files
for rel, content in files.items():
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")

# Compile all Python files and run unit tests before packaging.
import py_compile, subprocess, sys
for path in root.rglob("*.py"):
    py_compile.compile(str(path), doraise=True)

test_run = subprocess.run(
    [sys.executable, "-m", "unittest", "discover", "-s", "Tests", "-v"],
    cwd=str(root), capture_output=True, text=True
)
if test_run.returncode != 0:
    raise RuntimeError("Unit tests failed:\n" + test_run.stdout + test_run.stderr)

zip_path = Path("/mnt/data/HCDM1_Virtual_Test_Bench.zip")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for path in root.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts:
            zf.write(path, path.relative_to(root.parent))

print("Project created:", root)
print("ZIP created:", zip_path)
print("\nUnit test results:\n" + test_run.stdout + test_run.stderr)
