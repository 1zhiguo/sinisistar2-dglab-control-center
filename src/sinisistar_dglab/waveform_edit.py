"""Pure draft editing helpers for the 16-node waveform drawing surface.

All coordinates are normalized; y is amplitude, increasing upward. A pointer
move can cross many nodes between events, so every crossed node is filled.
"""
from __future__ import annotations

import math
from collections.abc import Iterable

NODES=16

def _unit(value):
    if type(value) not in (int,float) or not math.isfinite(value):
        raise ValueError('Waveform values must be finite numbers')
    return min(1.,max(0.,float(value)))

def sanitize_points(points: Iterable[float]) -> list[float]:
    try:values=list(points)
    except TypeError as exc:raise ValueError('Waveform needs 16 points') from exc
    if len(values)!=NODES:raise ValueError('Waveform needs 16 points')
    return [_unit(value) for value in values]

def apply_stroke(points,x0,y0,x1,y1) -> list[float]:
    values=sanitize_points(points)
    x0,y0,x1,y1=map(_unit,(x0,y0,x1,y1))
    if x0>x1:x0,y0,x1,y1=x1,y1,x0,y0
    first=math.floor(x0*(NODES-1)+.5)
    last=math.floor(x1*(NODES-1)+.5)
    if first==last:
        values[last]=y1
        return values
    distance=x1-x0
    for index in range(min(first,last),max(first,last)+1):
        fraction=min(1.,max(0.,(index/(NODES-1)-x0)/distance))
        values[index]=y0+(y1-y0)*fraction
    return values
