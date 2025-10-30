#!/usr/bin/env python3
"""Convert MusicXML into Core Keeper ocarina song text."""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import music21


POW2_DENOMS: List[int] = [1, 2, 4, 8, 16, 32, 64]

SEMITONE_NAMES = [
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "A#",
    "B",
]

NOTE_REGEX = re.compile(r"^([A-Ga-g])([#b]?)(\d+)$")


def note_name_to_midi(name: str) -> int:
    """Convert a note name like C#4 or Db4 to its MIDI number."""

    match = NOTE_REGEX.match(name.strip())
    if not match:
        raise ValueError(f"Cannot parse note name '{name}'")
    letter = match.group(1).upper()
    accidental = match.group(2)
    octave = int(match.group(3))
    key = letter + accidental.upper()
    if key.endswith("B") and len(key) == 2:
        enharmonic = {
            "CB": "B",
            "DB": "C#",
            "EB": "D#",
            "FB": "E",
            "GB": "F#",
            "AB": "G#",
            "BB": "A#",
        }
        key = enharmonic.get(key, letter)
    semitone = {
        "C": 0,
        "C#": 1,
        "D": 2,
        "D#": 3,
        "E": 4,
        "F": 5,
        "F#": 6,
        "G": 7,
        "G#": 8,
        "A": 9,
        "A#": 10,
        "B": 11,
    }.get(key)
    if semitone is None:
        raise ValueError(f"Unsupported note name '{name}'")
    return 12 * (octave + 1) + semitone


def midi_to_note_name(midi: int) -> str:
    """Return a canonical sharp-based note name from a MIDI number."""

    octave = (midi // 12) - 1
    semitone = midi % 12
    return f"{SEMITONE_NAMES[semitone]}{octave}"


def collect_midi_notes(score: music21.stream.Score) -> List[int]:
    notes: List[int] = []
    for element in score.flat.notes:
        if element.isChord:
            for p in element.pitches:
                notes.append(int(round(p.midi)))
        else:
            notes.append(int(round(element.pitch.midi)))
    return notes


def load_mapping_midis(path: Optional[Path]) -> List[int]:
    if not path:
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    midis: List[int] = []
    for note in data.keys():
        try:
            midis.append(note_name_to_midi(note))
        except ValueError:
            continue
    return midis


def choose_transpose(
    piece_midis: Sequence[int], mapping_midis: Sequence[int], manual: Optional[int]
) -> int:
    if manual is not None:
        return manual
    if not piece_midis:
        return 0
    if not mapping_midis:
        return 0
    min_piece = min(piece_midis)
    max_piece = max(piece_midis)
    min_map = min(mapping_midis)
    max_map = max(mapping_midis)
    best_shift: Optional[int] = None
    best_penalty: Optional[int] = None
    for shift in range(-60, 61):
        new_min = min_piece + shift
        new_max = max_piece + shift
        under = max(0, min_map - new_min)
        over = max(0, new_max - max_map)
        penalty = under + over
        if best_penalty is None or penalty < best_penalty or (
            penalty == best_penalty and best_shift is not None and abs(shift) < abs(best_shift)
        ) or (penalty == best_penalty and best_shift is None):
            best_penalty = penalty
            best_shift = shift
        if penalty == 0 and abs(shift) == 0:
            break
    return best_shift or 0


def fraction_to_spec(value: Fraction) -> str:
    """Return a duration specifier like '4+8' for a quarter-length fraction."""

    remaining = value.limit_denominator(64)
    parts: List[str] = []
    for denom in POW2_DENOMS:
        part = Fraction(4, denom)
        while remaining >= part:
            parts.append(str(denom))
            remaining -= part
    if remaining:
        raise ValueError(f"Cannot represent duration {float(value)} quarter lengths")
    return "+".join(parts)


def fold_into_range(midi: int, bounds: Optional[Tuple[int, int]]) -> Tuple[int, bool]:
    if not bounds:
        return midi, False
    low, high = bounds
    adjusted = midi
    changed = False
    if low > high:
        raise ValueError("Invalid mapping range; lower bound exceeds upper bound")
    while adjusted < low:
        adjusted += 12
        changed = True
    while adjusted > high:
        adjusted -= 12
        changed = True
    if not 0 <= adjusted <= 127:
        raise ValueError("Folded 음이 MIDI 범위를 벗어났습니다. 매핑 범위를 확인하세요.")
    return adjusted, changed


def extract_events(
    stream: music21.stream.Stream,
    semitone_shift: int,
    fold_bounds: Optional[Tuple[int, int]],
) -> Tuple[List[str], int]:
    folded = 0
    changes: Dict[Fraction, Dict[str, List[int]]] = defaultdict(lambda: {"add": [], "remove": []})
    timepoints = {Fraction(0)}

    def to_fraction(value: float) -> Fraction:
        return Fraction(value).limit_denominator(64)

    for element in stream.flat.notesAndRests:
        duration = to_fraction(element.duration.quarterLength)
        if duration == 0:
            continue
        start = to_fraction(element.offset)
        end = start + duration
        timepoints.add(start)
        timepoints.add(end)
        if element.isRest:
            continue

        pitches = element.pitches if element.isChord else [element.pitch]
        for pitch in pitches:
            midi = int(round(pitch.midi)) + semitone_shift
            if not 0 <= midi <= 127:
                raise ValueError(f"Pitch {pitch} shifted by {semitone_shift} is outside MIDI range")
            midi, changed = fold_into_range(midi, fold_bounds)
            if changed:
                folded += 1
            changes[start]["add"].append(midi)
            changes[end]["remove"].append(midi)

    ordered_times = sorted(timepoints)
    events: List[str] = []
    active: Counter[int] = Counter()

    for idx, current in enumerate(ordered_times[:-1]):
        delta = ordered_times[idx + 1] - current
        if delta <= 0:
            continue

        # Retire any notes ending at this offset before starting new ones
        for midi in changes[current]["remove"]:
            active[midi] -= 1
            if active[midi] <= 0:
                del active[midi]

        for midi in changes[current]["add"]:
            active[midi] += 1

        spec = fraction_to_spec(delta)
        if not active:
            events.append(f"R:{spec}")
            continue

        names = sorted({midi_to_note_name(midi) for midi in active.keys()})
        events.append(f"{'+'.join(names)}:{spec}")

    return events, folded


def detect_bpm(score: music21.stream.Score) -> Optional[int]:
    for _span, _end, mark in score.metronomeMarkBoundaries():
        if not mark:
            continue
        # Prefer the tempo converted to quarter-note BPM so dotted/eighth
        # references from the score do not slow playback.
        try:
            quarter_bpm = mark.getQuarterBPM()
        except AttributeError:
            quarter_bpm = None
        if quarter_bpm:
            return int(round(quarter_bpm))
        if mark.number:
            beat = getattr(mark, "beatDuration", None)
            if beat and beat.quarterLength:
                return int(round(mark.number * (1 / beat.quarterLength)))
            return int(round(mark.number))
    return None


def convert(
    input_path: Path,
    output_path: Path,
    mapping_path: Optional[Path] = None,
    manual_transpose: Optional[int] = None,
) -> int:
    score = music21.converter.parse(str(input_path))
    bpm = detect_bpm(score)
    piece_midis = collect_midi_notes(score)
    mapping_midis = load_mapping_midis(mapping_path)
    semitone_shift = choose_transpose(piece_midis, mapping_midis, manual_transpose)
    fold_bounds: Optional[Tuple[int, int]] = None
    if mapping_midis:
        fold_bounds = (min(mapping_midis), max(mapping_midis))
    events, folded = extract_events(score, semitone_shift, fold_bounds)
    lines: List[str] = []
    if bpm:
        lines.append(f"BPM={bpm}")
    lines.extend(events)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if folded and mapping_midis:
        low, high = min(mapping_midis), max(mapping_midis)
        print(
            f"[INFO] {folded}개의 음이 옥타브 조정되어 매핑 범위({midi_to_note_name(low)}~{midi_to_note_name(high)})에 맞춰졌습니다.",
            file=sys.stderr,
        )
    return semitone_shift


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="MusicXML file to convert")
    parser.add_argument("output", type=Path, help="Destination song file")
    default_map = Path(__file__).with_name("mapping.json")
    map_help = "mapping.json 파일 경로 (음역 자동 맞춤)"
    if default_map.exists():
        map_help += f" [기본값: {default_map.name}]"
    parser.add_argument(
        "--map",
        type=Path,
        default=default_map if default_map.exists() else None,
        help=map_help,
    )
    parser.add_argument(
        "--no-map",
        action="store_true",
        help="매핑을 사용하지 않고 원본 음역을 그대로 둡니다 (옥타브 조정/자동 transpose 비활성화)",
    )
    parser.add_argument(
        "--transpose",
        type=int,
        default=None,
        help="강제로 적용할 반음 이동 값 (양수=올림, 음수=내림)",
    )
    args = parser.parse_args()
    mapping_path = None if args.no_map else args.map
    if mapping_path and not mapping_path.exists():
        parser.error(f"지정한 매핑 파일을 찾을 수 없습니다: {mapping_path}")
    shift = convert(args.input, args.output, mapping_path, args.transpose)
    if shift:
        print(f"Applied transpose of {shift:+d} semitones.")
    else:
        print("No transpose applied.")


if __name__ == "__main__":
    main()
