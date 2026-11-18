"""Fixed attack-v1 geometry; rounded representatives are the actual centers."""
from __future__ import annotations
from dataclasses import dataclass
import math
import time
from protection.models import AttackSettings, coordinate_units, integer, finite, ids_tuple, require


@dataclass(frozen=True)
class AttackCandidate:
    id: int
    x: float
    y: float
    damaged_edge_ids: tuple[int, ...]

    def __post_init__(self):
        integer(self.id, 'attack id')
        finite(self.x, 'attack x', 0, 1)
        finite(self.y, 'attack y', 0, 1)
        ids_tuple(self.damaged_edge_ids)


@dataclass(frozen=True)
class PreparedAttacks:
    scenario_id: str
    attack_settings: AttackSettings
    policy_version: str
    candidates: tuple[AttackCandidate, ...]
    preparation_seconds: float

    def __post_init__(self):
        require(type(self.candidates) is tuple and bool(self.candidates), 'attack candidates required')
        require(all(type(c) is AttackCandidate and c.id == i for i, c in enumerate(self.candidates)), 'invalid attack ids')
        coords = tuple((c.x, c.y) for c in self.candidates)
        require(coords == tuple(sorted(set(coords))), 'attack coordinates must be sorted and unique')
        finite(self.preparation_seconds, 'preparation_seconds', 0)


def unique_coordinates(points):
    units = {(coordinate_units(x), coordinate_units(y)) for x, y in points}
    return tuple((x / 10**9, y / 10**9) for x, y in sorted(units))


def segment_distance(point, start, end):
    px, py = point
    ax, ay = start
    dx, dy = end[0] - ax, end[1] - ay
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0., min(1., ((px - ax) * dx + (py - ay) * dy) / length_squared))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def is_hit(point, start, end, settings=AttackSettings()):
    return segment_distance(point, start, end) <= settings.radius + settings.distance_tolerance


def prepare_attacks(scenario):
    started = time.monotonic()
    points = [(n.x, n.y) for n in scenario.nodes]
    for e in scenario.edges:
        u, v = scenario.nodes[e.u], scenario.nodes[e.v]
        points.append(((u.x + v.x) / 2, (u.y + v.y) / 2))
    denominator = scenario.attack_settings.grid_denominator
    points.extend((i / denominator, j / denominator)
                  for i in range(denominator + 1) for j in range(denominator + 1))
    candidates = []
    for i, point in enumerate(unique_coordinates(points)):
        damaged = tuple(e.id for e in scenario.edges if is_hit(
            point, (scenario.nodes[e.u].x, scenario.nodes[e.u].y),
            (scenario.nodes[e.v].x, scenario.nodes[e.v].y), scenario.attack_settings))
        candidates.append(AttackCandidate(i, *point, damaged))
    return PreparedAttacks(scenario.scenario_id, scenario.attack_settings, scenario.evaluation_policy.version,
                           tuple(candidates), time.monotonic() - started)


def surviving_ids(scenario, candidate, protected_ids):
    removed = set(candidate.damaged_edge_ids) - set(protected_ids)
    return tuple(e.id for e in scenario.edges if e.id not in removed)
