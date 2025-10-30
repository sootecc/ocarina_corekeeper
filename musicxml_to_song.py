#!/usr/bin/env python3
"""Convert MusicXML into Core Keeper ocarina song text."""

import argparse
import json
import re
import sys
from fractions import Fraction
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

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


def choose_transpose(piece_midis: Sequence[int], mapping_midis: Sequence[int], manual: Optional[int]) -> int:
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


def extract_events(stream: music21.stream.Stream, semitone_shift: int) -> Iterable[str]:
    for element in stream.flat.notesAndRests:
        duration = Fraction(element.duration.quarterLength).limit_denominator(64)
        spec = fraction_to_spec(duration)
        if element.isRest:
            yield f"R:{spec}"
            continue
        if element.isChord:
            names = []
            for pitch in element.pitches:
                midi = int(round(pitch.midi)) + semitone_shift
                if not 0 <= midi <= 127:
                    raise ValueError(f"Pitch {pitch} shifted by {semitone_shift} is outside MIDI range")
                names.append(midi_to_note_name(midi))
        else:
            midi = int(round(element.pitch.midi)) + semitone_shift
            if not 0 <= midi <= 127:
                raise ValueError(f"Pitch {element.pitch} shifted by {semitone_shift} is outside MIDI range")
            names = [midi_to_note_name(midi)]
        yield f"{'+'.join(names)}:{spec}"


def detect_bpm(score: music21.stream.Score) -> Optional[int]:
    for _span, _end, mark in score.metronomeMarkBoundaries():
        if mark.number:
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
    events = list(extract_events(score, semitone_shift))
    lines: List[str] = []
    if bpm:
        lines.append(f"BPM={bpm}")
    lines.extend(events)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if mapping_midis and piece_midis:
        new_min = min(piece_midis) + semitone_shift
        new_max = max(piece_midis) + semitone_shift
        if new_min < min(mapping_midis) or new_max > max(mapping_midis):
            print(
                "[WARN] 일부 음이 매핑 범위를 벗어났습니다. mapping.json을 확장하거나 수동 transpose를 조정하세요.",
                file=sys.stderr,
            )
    return semitone_shift


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="MusicXML file to convert")
    parser.add_argument("output", type=Path, help="Destination song file")
    parser.add_argument("--map", type=Path, default=None, help="mapping.json 파일 경로 (음역 자동 맞춤)")
    parser.add_argument(
        "--transpose",
        type=int,
        default=None,
        help="강제로 적용할 반음 이동 값 (양수=올림, 음수=내림)",
    )
    args = parser.parse_args()
    shift = convert(args.input, args.output, args.map, args.transpose)
    if shift:
        print(f"Applied transpose of {shift:+d} semitones.")
    else:
        print("No transpose applied.")


if __name__ == "__main__":
    main()
