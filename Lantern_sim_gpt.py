from pathlib import Path
import zipfile, py_compile, subprocess, sys

base = Path("/mnt/data/HCDM1_Virtual_Test_Bench")
for folder in ("Common", "Simulation", "Tests"):
    (base / folder).mkdir(parents=True, exist_ok=True)

src = {
"Common/__init__.py": "",
"Simulation/__init__.py": "",
"Common/protocol.py": '''PACKET_LENGTH = 16

def crc16_ccitt(data, initial=0xFFFF):
    crc = initial
    for b in data:
        crc ^= (b & 255) << 8
        for _ in range(8):
            crc = (((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)) & 0xFFFF
    return crc

def encode_packet(groups, motor, sequence):
    if len(groups) != 4 or any(len(g) != 3 for g in groups):
        raise ValueError("Expected four RGB triples")
    data = bytearray(int(v) for g in groups for v in g)
    if any(v < 0 or v > 255 for v in data):
        raise ValueError("RGB values must be 0..255")
    data.extend((1 if motor else 0, int(sequence) & 255))
    crc = crc16_ccitt(data)
    data.extend((crc >> 8, crc & 255))
    return bytes(data)

def decode_packet(packet):
    packet = bytes(packet)
    if len(packet) != 16:
        raise ValueError("Bad packet length")
    if crc16_ccitt(packet[:14]) != ((packet[14] << 8) | packet[15]):
        raise ValueError("CRC mismatch")
    return {"rgb_groups": [tuple(packet[i:i+3]) for i in range(0,12,3)],
            "motor": bool(packet[12] & 1), "sequence": packet[13]}

def packet_to_symbols(packet):
    if len(packet) != 16:
        raise ValueError("Expected 16 bytes")
    return [(b >> s) & 3 for b in packet for s in (6,4,2,0)]

def symbols_to_burst_groups(packet):
    return [8] + [x + 1 for x in packet_to_symbols(packet)]

def packet_hex(packet):
    return " ".join("%02X" % b for b in packet)
''',
"Common/dmx.py": '''PERSONALITY_CHANNELS = 13
def address_from_dips(dips):
    if len(dips) != 9:
        raise ValueError("Need nine address DIP states")
    return sum((1 << i) for i, on in enumerate(dips) if on)
def valid_start_address(address):
    return 1 <= int(address) <= 500
def decode_personality(universe, start_address):
    if len(universe) < 512 or not valid_start_address(start_address):
        raise ValueError("Invalid DMX universe or start address")
    v = [int(x) & 255 for x in universe[start_address-1:start_address+12]]
    return [tuple(v[i:i+3]) for i in (0,3,6,9)], v[12] >= 128
''',
"Tests/test_protocol.py": '''import unittest
from Common.protocol import *
class TestProtocol(unittest.TestCase):
    def test_crc_vector(self): self.assertEqual(crc16_ccitt(b"123456789"), 0x29B1)
    def test_roundtrip(self):
        g=[(1,2,3),(4,5,6),(7,8,9),(10,11,12)]
        d=decode_packet(encode_packet(g,True,19))
        self.assertEqual(d["rgb_groups"],g); self.assertTrue(d["motor"]); self.assertEqual(d["sequence"],19)
    def test_corrupt(self):
        p=bytearray(encode_packet([(0,0,0)]*4,False,0)); p[0]^=1
        with self.assertRaises(ValueError): decode_packet(p)
if __name__ == "__main__": unittest.main()
''',
"Tests/test_dmx.py": '''import unittest
from Common.dmx import *
class TestDMX(unittest.TestCase):
    def test_address(self): self.assertEqual(address_from_dips([1,0,1,0,0,1,1,0,0]),101)
    def test_range(self): self.assertTrue(valid_start_address(500)); self.assertFalse(valid_start_address(501))
    def test_decode(self):
        u=[0]*512; u[99:112]=list(range(13))
        g,m=decode_personality(u,100); self.assertEqual(g,[(0,1,2),(3,4,5),(6,7,8),(9,10,11)]); self.assertFalse(m)
if __name__ == "__main__": unittest.main()
''',
"Simulation/simulator.py": '''import tkinter as tk
from tkinter import ttk
import random
from Common.dmx import address_from_dips, valid_start_address, decode_personality
from Common.protocol import encode_packet, decode_packet, packet_hex, symbols_to_burst_groups

INTERVAL=1500
TIMEOUT=15000
class Prop:
    def __init__(self,n):
        self.n=n; self.mode=False; self.block=False; self.corrupt=0; self.sensors=[True]*4
        self.rgb=[(0,0,255)]*4; self.motor=False; self.last=None; self.seq=None
        self.accept=0; self.reject=0; self.lost=0; self.timeout=True
    def rx(self,p,now,rng):
        if self.block or not any(self.sensors): self.lost+=1; return "link/sensors unavailable"
        q=bytearray(p)
        if rng.random()<self.corrupt/100: q[rng.randrange(14)] ^= 1
        try: d=decode_packet(q)
        except ValueError: self.reject+=1; return "CRC rejected"
        if d["sequence"]==self.seq and self.last is not None and now-self.last<5000: return "duplicate"
        self.rgb=d["rgb_groups"]; self.motor=d["motor"]; self.seq=d["sequence"]
        self.last=now; self.timeout=False; self.accept+=1; return "accepted"
    def tick(self,now):
        if self.last is None or now-self.last>=TIMEOUT:
            self.rgb=[(0,0,255)]*4; self.motor=False; self.timeout=True

class App:
    def __init__(self,root):
        self.root=root; root.title("HCDM-1 Virtual Test Bench"); root.geometry("1300x900")
        self.now=0; self.seq=0; self.lasttx=-INTERVAL; self.rng=random.Random()
        self.dips=[tk.BooleanVar() for _ in range(9)]; self.ir=tk.BooleanVar(value=True)
        self.dmx_on=tk.BooleanVar(value=True); self.universe=[0]*512; self.channels=[tk.IntVar() for _ in range(13)]
        self.props=[Prop(i+1) for i in range(4)]; self.cards=[]; self.running=False
        self.build(); self.refresh()
    def build(self):
        top=ttk.Frame(self.root,padding=8); top.pack(fill="x")
        self.clock=tk.StringVar(); ttk.Label(top,textvariable=self.clock,font=("Arial",11,"bold")).pack(side="left",padx=8)
        self.runbtn=ttk.Button(top,text="Start",command=self.toggle); self.runbtn.pack(side="left")
        for label,ms in (("Step 100 ms",100),("Step 1 s",1000),("Step 15 s",15000)):
            ttk.Button(top,text=label,command=lambda x=ms:self.advance(x)).pack(side="left",padx=3)
        ttk.Button(top,text="Send IR",command=self.tx).pack(side="left")
        ttk.Button(top,text="Reset",command=self.reset).pack(side="left")
        panes=ttk.Panedwindow(self.root,orient="horizontal"); panes.pack(fill="both",expand=True,padx=8,pady=8)
        left=ttk.Frame(panes,padding=8); right=ttk.Frame(panes,padding=8); panes.add(left,weight=1); panes.add(right,weight=2)
        dips=ttk.LabelFrame(left,text="Transmitter DIP switches",padding=8); dips.pack(fill="x")
        for i,v in enumerate(self.dips): ttk.Checkbutton(dips,text=str(i+1),variable=v,command=self.refresh).grid(row=0,column=i)
        ttk.Checkbutton(dips,text="DIP 10: IR enabled",variable=self.ir).grid(row=1,column=0,columnspan=4,sticky="w")
        ttk.Checkbutton(dips,text="DMX present",variable=self.dmx_on).grid(row=1,column=4,columnspan=3,sticky="w")
        self.addr=tk.StringVar(); ttk.Label(dips,textvariable=self.addr).grid(row=2,column=0,columnspan=9,sticky="w")
        ch=ttk.LabelFrame(left,text="13-channel DMX personality",padding=8); ch.pack(fill="both",expand=True,pady=8)
        names=["G1 R","G1 G","G1 B","G2 R","G2 G","G2 B","G3 R","G3 G","G3 B","G4 R","G4 G","G4 B","Motor"]
        for i,name in enumerate(names):
            ttk.Label(ch,text=name,width=8).grid(row=i,column=0,sticky="w")
            s=ttk.Scale(ch,from_=0,to=255,command=lambda x,j=i:self.setch(j,x)); s.grid(row=i,column=1,sticky="ew")
            self.channels[i].set(0); self.channels[i].trace_add("write",lambda *a:self.update_dmx())
        ch.columnconfigure(1,weight=1)
        ttk.Label(left,text="38 kHz modeled carrier | 600 µs burst | 1.5 s frame interval\\n16-byte packet | CRC-16/CCITT | 15 s receiver fallback").pack(anchor="w")
        propgrid=ttk.Frame(right); propgrid.pack(fill="both",expand=True)
        for i,p in enumerate(self.props):
            box=ttk.LabelFrame(propgrid,text="Virtual Prop %d"%p.n,padding=8)
            box.grid(row=i//2,column=i%2,sticky="nsew",padx=4,pady=4)
            propgrid.columnconfigure(i%2,weight=1); propgrid.rowconfigure(i//2,weight=1)
            mode=tk.BooleanVar(); block=tk.BooleanVar(); corrupt=tk.IntVar()
            ttk.Checkbutton(box,text="Mode B: reverse groups",variable=mode,command=lambda p=p,m=mode:setattr(p,"mode",m.get())).pack(anchor="w")
            ttk.Checkbutton(box,text="Block IR link",variable=block,command=lambda p=p,b=block:setattr(p,"block",b.get())).pack(anchor="w")
            row=ttk.Frame(box); row.pack(anchor="w")
            ttk.Label(row,text="Corruption %").pack(side="left")
            ttk.Spinbox(row,from_=0,to=100,width=5,textvariable=corrupt,command=lambda p=p,c=corrupt:setattr(p,"corrupt",c.get())).pack(side="left")
            sens=[]
            sr=ttk.Frame(box); sr.pack(anchor="w")
            ttk.Label(sr,text="Sensors").pack(side="left")
            for j in range(4):
                v=tk.BooleanVar(value=True); sens.append(v)
                ttk.Checkbutton(sr,text=str(j+1),variable=v,command=lambda p=p,ss=sens:setattr(p,"sensors",[x.get() for x in ss])).pack(side="left")
            leds=ttk.Frame(box); leds.pack(fill="x",pady=5)
            sw=[]
            for j in range(4):
                w=tk.Label(leds,text="G%d"%(j+1),bg="#0000ff",fg="white",relief="groove",width=7); w.pack(side="left",expand=True,fill="x",padx=2); sw.append(w)
            status=tk.StringVar(); ttk.Label(box,textvariable=status,wraplength=360).pack(anchor="w")
            self.cards.append((sw,status))
        logbox=ttk.LabelFrame(right,text="Event log and packet diagnostics",padding=5); logbox.pack(fill="both")
        self.log=tk.Text(logbox,height=11,state="disabled",font=("Consolas",9)); self.log.pack(fill="both",expand=True)
        self.write("Ready. Logical simulation only; hardware timing and optical performance are not validated.")
    def setch(self,i,x): self.channels[i].set(int(float(x)))
    def update_dmx(self):
        a=address_from_dips([v.get() for v in self.dips])
        if valid_start_address(a):
            for i,v in enumerate(self.channels): self.universe[a-1+i]=v.get()
    def values(self):
        a=address_from_dips([v.get() for v in self.dips])
        if not valid_start_address(a): return [(0,0,0)]*4,False,False
        g,m=decode_personality(self.universe,a)
        fresh=self.dmx_on.get() and self.now<=1000
        return g,m and fresh,fresh
    def tx(self):
        if not self.ir.get(): self.write("TX skipped: DIP 10 disabled."); return
        g,m,f=self.values(); p=encode_packet(g,m,self.seq)
        self.write("TX seq=%d addr=%d DMX=%s motor=%s"%(self.seq,address_from_dips([v.get() for v in self.dips]),"fresh" if f else "stale","ON" if m else "OFF"))
        self.write("Packet: "+packet_hex(p)+" | logical burst groups: "+str(len(symbols_to_burst_groups(p))))
        for prop in self.props: self.write(" Prop %d: %s"%(prop.n,prop.rx(p,self.now,self.rng)))
        self.seq=(self.seq+1)&255; self.lasttx=self.now; self.refresh()
    def advance(self,ms):
        end=self.now+ms
        while self.now<end:
            self.now=min(end,self.now+100)
            if self.ir.get() and self.now-self.lasttx>=INTERVAL: self.tx()
            for p in self.props:
                old=p.timeout; p.tick(self.now)
                if p.timeout and not old: self.write("Prop %d timeout: blue / motor OFF"%p.n)
        self.refresh()
    def toggle(self):
        self.running=not self.running; self.runbtn.configure(text="Pause" if self.running else "Start")
        if self.running: self.auto()
    def auto(self):
        if self.running: self.advance(100); self.root.after(100,self.auto)
    def reset(self):
        self.running=False; self.runbtn.configure(text="Start"); self.now=0; self.seq=0; self.lasttx=-INTERVAL
        self.universe=[0]*512
        for c in self.channels:c.set(0)
        self.props=[Prop(i+1) for i in range(4)]
        self.write("Simulation reset."); self.refresh()
    def refresh(self):
        a=address_from_dips([v.get() for v in self.dips]); self.addr.set("DMX start address: %d — %s"%(a,"VALID" if valid_start_address(a) else "INVALID (1–500)"))
        self.clock.set("Virtual time: %.1f s"%(self.now/1000))
        for p,(sw,status) in zip(self.props,self.cards):
            groups=list(reversed(p.rgb)) if p.mode else p.rgb
            for w,c in zip(sw,groups): w.configure(bg="#%02x%02x%02x"%c,fg="white" if sum(c)<380 else "black")
            status.set(("TIMEOUT FALLBACK — blue; " if p.timeout else "Receiving; ")+"Motor %s | RX %d | CRC reject %d | lost %d"%( "ON" if p.motor else "OFF",p.accept,p.reject,p.lost))
    def write(self,s):
        self.log.configure(state="normal"); self.log.insert("end","[%7.1fs] %s\\n"%(self.now/1000,s)); self.log.see("end"); self.log.configure(state="disabled")

def main():
    root=tk.Tk(); App(root); root.mainloop()
if __name__=="__main__": main()
''',
"README.md": '''# HCDM-1 Virtual Test Bench

Desktop Python/Tkinter project for logical simulation before hardware is available.

## Run in PyCharm
1. Extract this ZIP and open the `HCDM1_Virtual_Test_Bench` folder.
2. Use a normal desktop Python 3.10+ interpreter.
3. Run `Simulation/simulator.py` with the green Run button.
4. No pip packages are required. Tkinter is normally bundled with Python.

## Tests
From the project root:
`python -m unittest discover -s Tests -v`

## Included
- Transmitter with DIP 1–9 binary DMX address and DIP 10 IR enable.
- 13-channel DMX personality: four RGB groups and motor threshold >=128.
- 16-byte packet and CRC-16/CCITT.
- Four virtual props, each with four independently disableable sensors.
- Per-prop Mode B reverse mapping, link blocking, packet corruption, counters.
- 1.5-second transmit cadence and 15-second blue/motor-off timeout fallback.
- Manual virtual-time stepping, auto-run, event log, and packet hex diagnostics.

## Important limitations
This is a logical software model, not a physical hardware emulator. It does not validate actual IR carrier timing, TSSP77038 pulse behavior, emitter range, ambient-light immunity, DMX/RS-485 waveforms, WS2812 timing/power, motor-driver ratings, MicroPython scheduling, or power-loss storage behavior. The proposed optical burst protocol must be tested on real hardware with a logic analyzer before PCB fabrication. The 38 kHz, 600 µs, and packet timing values are design assumptions only.
''',
"requirements.txt": "# Standard library only; no pip packages required.\\n",
"run_tests.bat": "@echo off\\ncd /d %~dp0\\npython -m unittest discover -s Tests -v\\npause\\n",
"run_simulator.bat": "@echo off\\ncd /d %~dp0\\npython Simulation\\\\simulator.py\\npause\\n",
}

for rel, text in src.items():
    (base / rel).write_text(text, encoding="utf-8")

for p in base.rglob("*.py"):
    py_compile.compile(str(p), doraise=True)

test = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "Tests", "-v"],
                      cwd=base, capture_output=True, text=True)
if test.returncode:
    raise RuntimeError(test.stdout + test.stderr)

zip_path = Path("/mnt/data/HCDM1_Virtual_Test_Bench.zip")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for p in base.rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts:
            z.write(p, p.relative_to(base.parent))

print("Created:", zip_path)
print(test.stdout + test.stderr)
