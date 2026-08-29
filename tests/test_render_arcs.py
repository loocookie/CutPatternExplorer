"""렌더 계층 테스트. 설계 문서 §11."""

import math

import numpy as np
import pytest

from cutpattern.dsl import AxisSet
from cutpattern.engine.axes import PuzzleFamily
from cutpattern.engine.operations import SplitByAxis, Turn, evaluate
from cutpattern.render.arcs import arc_id, build_arcs

FACE_NORMALS = [
    ("U", (0, 1, 0)),
    ("D", (0, -1, 0)),
    ("R", (1, 0, 0)),
    ("L", (-1, 0, 0)),
    ("F", (0, 0, 1)),
    ("B", (0, 0, -1)),
]

ALL_FACE_SPLITS = tuple(SplitByAxis(i) for i in ("R", "L", "U", "D", "F", "B"))
THETA_333 = math.degrees(math.acos(1.0 / math.sqrt(3.0)))
FACES = AxisSet(id="faces", axes=dict(FACE_NORMALS), name="면축")


def build(*ops, theta=THETA_333, max_step=0.05):
    fam = PuzzleFamily(axis_sets=(FACES.to_engine(),), operations=tuple(ops))
    reg, _ = evaluate(fam, {"faces": theta})
    return reg, build_arcs(reg, max_step=max_step)


def test_static_pattern_gives_six_full_circles():
    _reg, arcs = build(*ALL_FACE_SPLITS)
    assert len(arcs) == 6
    assert all(a.is_full_circle for a in arcs)


def test_all_points_lie_on_unit_sphere_and_carrier_plane():
    _reg, arcs = build(*ALL_FACE_SPLITS, Turn("U", 45.0), SplitByAxis("R"))
    for a in arcs:
        assert np.allclose(np.linalg.norm(a.points, axis=1), 1.0)
        assert np.allclose(np.asarray(a.points) @ a.circle.n, a.circle.h)


def test_arc_id_is_deterministic_across_reevaluation():
    """같은 입력으로 replay 하면 같은 ID. 렌더 객체 pool 의 전제 (§11)."""
    _r1, a1 = build(*ALL_FACE_SPLITS, Turn("U", 45.0), SplitByAxis("R"))
    _r2, a2 = build(*ALL_FACE_SPLITS, Turn("U", 45.0), SplitByAxis("R"))
    assert [a.id for a in a1] == [a.id for a in a2]
    assert len(set(a.id for a in a1)) == len(a1)


def test_arc_id_does_not_depend_on_angle_values():
    assert arc_id(3, 1, 0) == "c3:o1:0"


def test_provenance_reaches_the_renderer():
    _reg, arcs = build(*ALL_FACE_SPLITS, Turn("U", 45.0))
    kinds = {a.provenance.kind for a in arcs}
    assert kinds == {"split", "turn"}


def test_tessellation_step_controls_point_count():
    """slider 조작 중에는 성기게, 종료 후에는 촘촘하게 (§12-4)."""
    _r, coarse = build(*ALL_FACE_SPLITS, max_step=0.5)
    _r, fine = build(*ALL_FACE_SPLITS, max_step=0.02)
    assert sum(len(a.points) for a in fine) > 5 * sum(len(a.points) for a in coarse)


def test_degenerate_carrier_is_skipped():
    _reg, arcs = build(*ALL_FACE_SPLITS, theta=0.01)
    assert arcs  # 0.01도는 아주 작지만 퇴화는 아니다
    assert all(a.circle.r > 0 for a in arcs)


# ---- 축 집합별 색칠의 근거 ----------------------------------------------


def test_every_arc_knows_its_originating_axis_set():
    """재료를 만드는 연산은 Split 뿐이므로 모든 호가 출처를 가진다 (§5, §11)."""
    _reg, arcs = build(*ALL_FACE_SPLITS, Turn("U", 45.0), SplitByAxis("R"))
    assert arcs
    assert all(a.provenance.origin_axis_set == "faces" for a in arcs)
    assert all(a.provenance.origin_axis for a in arcs)


def test_turn_preserves_origin_but_updates_mover():
    """Turn 은 옮긴 연산만 갱신하고 출처는 물려준다."""
    _reg, arcs = build(*ALL_FACE_SPLITS, Turn("U", 45.0))
    turned = [a for a in arcs if a.provenance.kind == "turn"]
    assert turned
    for a in turned:
        assert a.provenance.axis_id == "U"       # 옮긴 축
        assert a.provenance.origin_axis != "U"   # 만든 축은 다르다
        assert a.provenance.origin_axis_set == "faces"


def test_two_axis_sets_keep_separate_origins():
    """축 집합이 둘이면 호가 각자의 집합을 기억해야 색이 갈린다."""
    edges = AxisSet("edges", axes={"E1": (1, 1, 0), "E2": (1, 0, 1)})
    fam = PuzzleFamily(
        axis_sets=(FACES.to_engine(), edges.to_engine()),
        operations=(
            *ALL_FACE_SPLITS,
            *[SplitByAxis(a.id) for a in edges],
            Turn("U", 45.0),
        ),
    )
    reg, _ = evaluate(fam, {"faces": THETA_333, "edges": 70.0})
    arcs = build_arcs(reg)
    origins = {a.provenance.origin_axis_set for a in arcs}
    assert origins == {"faces", "edges"}
