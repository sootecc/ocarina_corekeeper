#!/usr/bin/env python3
"""
Core Keeper Ocarina Auto-Player
Mode: Chromatic, 2-octave lanes, chords, hold/strum/repeat
----------------------------------------------------------------
New in this version
- **Chords**: notes joined by '+' (e.g., C+E+G:4)
- **Hold**: key hold duration per-chord or per-note `(h0.15)` (seconds)
- **Strum/Stagger**: chord spread `(st0.01)` between note downs (sec)
- **Repeat (multi-click)**: `(rep3)` splits duration into 3 re-triggers
- **Headers**: set defaults anywhere: HOLD=0.12, STAGGER=0.008, REP=1
- Keeps support for: LOW/HIGH lanes, dotted/added durations, TEMPO/UNIT
Examples are in README.
"""
import time, re, json, sys
from typing import Dict, List, Tuple

try:
    import pyautogui
except ImportError:
    print("Missing dependency: pyautogui\nInstall with: pip install pyautogui")
    sys.exit(1)

ENHARMONIC = {"DB":"C#","EB":"D#","GB":"F#","AB":"G#","BB":"A#","E#":"F","B#":"C"}

def norm_note(raw: str, default_oct: int) -> str:
    t = raw.strip()
    if t.upper() == "R": return "R"
    m = re.match(r'^([A-Ga-g])([#b]?)(\d*)$', t)
    if not m: raise ValueError(f"Bad note '{raw}'")
    name = m.group(1).upper(); acc = m.group(2); octv = m.group(3)
    if acc == 'b':
        key = (name+'B').upper()
        s = ENHARMONIC.get(key, None)
        if s: name = s[0]; acc = '#'
        else: acc = ''  # fallback
    octave = int(octv) if octv else int(default_oct)
    return f"{name}{acc}{octave}"

def parse_header(line: str, state: dict) -> bool:
    up = line.strip().upper()
    if up.startswith(("BPM=","TEMPO=")):
        bpm = int(up.split("=",1)[1]); state["bpm"]=bpm; state["q"]=60.0/bpm; return True
    if up.startswith("UNIT="): state["unit"]=int(up.split("=",1)[1]); return True
    if up.startswith("HOLD="): state["hold"]=float(up.split("=",1)[1]); return True
    if up.startswith("STAGGER="): state["stagger"]=float(up.split("=",1)[1]); return True
    if up.startswith("REP="): state["rep"]=int(up.split("=",1)[1]); return True
    return False

def parse_duration(spec: str, unit: int, q: float, dots: int) -> float:
    if spec == "": total = q*(4.0/unit)
    else:
        total = 0.0
        for p in spec.split('+'): total += q*(4.0/int(p))
    for _ in range(dots): total *= 1.5
    return total

ATTR_RE = re.compile(r'\((?P<body>[^)]*)\)')
def parse_attrs(attr_str: str) -> dict:
    """
    Attributes: h0.15 (hold seconds), st0.01 (stagger), rep3 (repeat count)
    Multiple allowed comma-separated: (h0.18,st0.01,rep2)
    """
    out = {}
    if not attr_str: return out
    for chunk in attr_str.split(','):
        c = chunk.strip()
        if not c: continue
        if c.startswith('h'): out["hold"] = float(c[1:])
        elif c.startswith('st'): out["stagger"] = float(c[2:])
        elif c.startswith('rep'): out["rep"] = int(c[3:])
    return out

def parse_song(path: str):
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
    if not lines: raise ValueError("Empty song")
    state = {"bpm":120, "q":0.5, "unit":8, "lane":"LOW", "hold":0.12, "stagger":0.008, "rep":1}
    idx = 0
    while idx < len(lines) and parse_header(lines[idx], state): idx+=1
    events = []  # list of dict: {notes:[C4..], dur, hold, stagger, rep}
    lane_oct = {"LOW":4, "HIGH":5}
    tok_re = re.compile(
        r'^(?P<notes>[A-Ga-gR](?:[#b]?\d*)?(?:\+[A-Ga-gR](?:[#b]?\d*)?)*)' # C or C+E+G
        r'(?::(?P<dur>[0-9+]+))?'                                         # :8 or :8+16
        r'(?P<dots>\.*)'                                                  # . or ..
        r'(?P<attr>\([^)]*\))?$'                                          # (h0.2,st0.01,rep2)
    )
    for line in lines[idx:]:
        if parse_header(line, state): continue
        # lane switches may be inline tokens; allow multiple per line
        tokens = line.replace("|"," ").replace(","," ").split()
        for raw in tokens:
            up = raw.upper()
            if up.startswith("LOW"): state["lane"]="LOW"; continue
            if up.startswith("HIGH"): state["lane"]="HIGH"; continue
            if up.startswith(("BPM=","TEMPO=","UNIT=","HOLD=","STAGGER=","REP=")):
                parse_header(up, state); continue
            m = tok_re.match(raw)
            if not m: raise ValueError(f"Bad token '{raw}'")
            notespec = m.group("notes")
            dur_spec = m.group("dur") or ""
            dots = len(m.group("dots") or "")
            attr = parse_attrs(m.group("attr")[1:-1] if m.group("attr") else "")
            dur = parse_duration(dur_spec, state["unit"], state["q"], dots)
            # build chord notes
            default_oct = lane_oct[state["lane"]]
            notes = [norm_note(n, default_oct) for n in notespec.split('+')]
            # merge attributes with state defaults
            ev = {
                "notes": notes,
                "dur": dur,
                "hold": float(attr.get("hold", state["hold"])),
                "stagger": float(attr.get("stagger", state["stagger"])),
                "rep": int(attr.get("rep", state["rep"])),
            }
            events.append(ev)
    return events, state

def chord_play(keys: List[str], hold: float, stagger: float):
    import pyautogui, time
    # press in order with stagger
    for i,k in enumerate(keys):
        pyautogui.keyDown(k); 
        if stagger>0 and i < len(keys)-1: time.sleep(stagger)
    # hold
    time.sleep(max(0.01, hold))
    # release in reverse with stagger
    for i,k in enumerate(reversed(keys)):
        pyautogui.keyUp(k)
        if stagger>0 and i < len(keys)-1: time.sleep(stagger)

def play(song_path: str, mapping_path: str, countdown: int = 4):
    with open(mapping_path, "r", encoding="utf-8") as f: mapping = json.load(f)
    events, state = parse_song(song_path)
    print(f"Loaded song '{song_path}' @ {state['bpm']} BPM, {len(events)} events.")
    print(f"Defaults: UNIT={state['unit']} HOLD={state['hold']} STAGGER={state['stagger']} REP={state['rep']}")
    print(f"You have {countdown} seconds to focus the Core Keeper window.")
    for i in range(countdown,0,-1): print(f"... starting in {i}"); time.sleep(1.0)
    print("Playing! (Ctrl+C to abort)")
    for ev in events:
        notes = ev["notes"]; dur = ev["dur"]; hold = ev["hold"]; st = ev["stagger"]; rep = max(1, ev["rep"])
        if notes == ["R"]:
            time.sleep(dur); continue
        keys = []
        missing = []
        for n in notes:
            if n=="R": continue
            k = mapping.get(n); 
            if not k: missing.append(n)
            else: keys.append(k)
        if missing:
            print(f"[WARN] Missing mapping for {missing}; resting {dur:.3f}s"); time.sleep(dur); continue
        # Repeat logic: split dur into rep slots
        slot = dur/rep
        for i in range(rep):
            used_hold = min(hold, max(0.01, slot-0.02))
            chord_play(keys, used_hold, st)
            rest = max(0.0, slot - used_hold)
            if rest>0: time.sleep(rest)
    print("Done.")

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Core Keeper Ocarina Auto-Player (chords+hold+repeat)")
    ap.add_argument("--song", default="song_chords.txt")
    ap.add_argument("--map", default="mapping.json")
    ap.add_argument("--countdown", type=int, default=4)
    args = ap.parse_args()
    try:
        play(args.song, args.map, args.countdown)
    except KeyboardInterrupt:
        print("\nAborted.")
    except Exception as e:
        print("Error:", e); sys.exit(1)

if __name__ == "__main__":
    main()
