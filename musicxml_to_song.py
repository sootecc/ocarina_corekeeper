#!/usr/bin/env python3
"""Convert MusicXML into Core Keeper ocarina song text."""

import argparse
from fractions import Fraction
from pathlib import Path
from typing import Iterable, List, Optional

import music21


POW2_DENOMS: List[int] = [1, 2, 4, 8, 16, 32, 64]


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


def extract_events(stream: music21.stream.Stream) -> Iterable[str]:
    for element in stream.flat.notesAndRests:
        duration = Fraction(element.duration.quarterLength).limit_denominator(64)
        spec = fraction_to_spec(duration)
        if element.isRest:
            yield f"R:{spec}"
            continue
        if element.isChord:
            names = [p.nameWithOctave.replace('-', 'b') for p in element.pitches]
        else:
            names = [element.pitch.nameWithOctave.replace('-', 'b')]
        yield f"{'+'.join(names)}:{spec}"


def detect_bpm(score: music21.stream.Score) -> Optional[int]:
    for _span, _end, mark in score.metronomeMarkBoundaries():
        if mark.number:
            return int(round(mark.number))
    return None


def convert(input_path: Path, output_path: Path) -> None:
    score = music21.converter.parse(str(input_path))
    bpm = detect_bpm(score)
    events = list(extract_events(score))
    lines: List[str] = []
    if bpm:
        lines.append(f"BPM={bpm}")
    lines.extend(events)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="MusicXML file to convert")
    parser.add_argument("output", type=Path, help="Destination song file")
    args = parser.parse_args()
    convert(args.input, args.output)


if __name__ == "__main__":
    main()
