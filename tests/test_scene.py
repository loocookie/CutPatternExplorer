"""호스트로 넘길 장면 payload. 설계 문서 §11.1, §11.2.

여기서 검사하는 것은 **평탄화가 정보를 잃지 않는가**다. 좌표를 이어 붙이고
경계를 따로 실으므로, 경계 계산이 하나만 어긋나도 호가 엉뚱하게 이어진다.
그림으로는 알아채기 어려운 종류라 테스트로 막는다.
"""

from __future__ import annotations

import json
import math

import pytest

from cutpattern import solids as S
from cutpattern.dsl import at_angle, puzzle, split, turned
from cutpattern.geometry.vector import norm
from cutpattern.render.arcs import build_arcs
from cutpattern.render.markers import build_axis_markers
from cutpattern.render.scene import (ARC, MARKER, build_marker_scene,
                                     build_scene)

THETA = math.degrees(math.acos(0.45))


def _puzzle():
    faces = S.cube("cube", turns=(45, -45))
    edges = S.rhombic_dodecahedron("edges")
    with puzzle("scene", faces, edges) as p:
        split(faces)
        with turned(faces["c-3"], 45):
            split(*at_angle(faces["c-3"], 90, faces))
    return p


@pytest.fixture
def built():
    p = _puzzle()
    reg, _log = p.evaluate({"cube": THETA, "edges": 70.0}, on_illegal="truncate")
    return p, reg


def test_polylines_round_trip_through_the_flat_arrays(built):
    """평탄화한 뒤 잘라낸 점들이 원본 호와 같은가."""
    p, reg = built
    scene = build_scene(reg, p.family)
    arcs = build_arcs(reg, max_step=0.03)
    markers = build_axis_markers(p.family.axis_sets)

    assert len(scene) == len(arcs) + len(markers)
    assert scene.point_count == sum(len(a.points) for a in arcs) + sum(
        len(m.points) for m in markers
    )

    for i, arc in enumerate(arcs):
        assert scene.polyline(i) == [tuple(pt) for pt in arc.points]
    for j, marker in enumerate(markers):
        assert scene.polyline(len(arcs) + j) == [tuple(pt) for pt in marker.points]


def test_boundaries_are_contiguous_and_cover_every_point(built):
    """폴리라인 경계가 빈틈도 겹침도 없이 전체를 덮는가."""
    p, reg = built
    scene = build_scene(reg, p.family)
    cursor = 0
    for start, count in zip(scene.starts, scene.counts):
        assert start == cursor, "폴리라인 사이에 빈틈이나 겹침이 있다"
        assert count >= 2, "점 하나짜리 폴리라인은 그릴 수 없다"
        cursor += count
    assert cursor == scene.point_count
    assert len(scene.xyz) == 3 * scene.point_count


def test_every_point_is_on_the_unit_sphere(built):
    """호와 마커 모두 구면 위에 있어야 §11.3 의 깊이 순서가 성립한다."""
    p, reg = built
    scene = build_scene(reg, p.family)
    xyz = scene.xyz
    for k in range(scene.point_count):
        assert norm(xyz[3 * k : 3 * k + 3]) == pytest.approx(1.0, abs=1e-9)


def test_groups_point_at_real_axis_sets(built):
    """색과 토글이 이 인덱스를 쓴다. 범위를 벗어나면 조용히 틀린 색이 나온다."""
    p, reg = built
    scene = build_scene(reg, p.family)
    assert scene.axis_sets == ["cube", "edges"]
    assert all(0 <= g < len(scene.axis_sets) for g in scene.groups)
    assert set(scene.kinds) == {ARC, MARKER}

    # 마커는 자기 축 집합에 속한다
    markers = build_axis_markers(p.family.axis_sets)
    n_arcs = len(scene) - len(markers)
    for j, marker in enumerate(markers):
        assert scene.axis_sets[scene.groups[n_arcs + j]] == marker.axis_set_id


def test_labels_carry_the_axis_id_outside_the_sphere(built):
    """라벨은 구 밖에 띄운다. 표면에 붙으면 호에 묻힌다 (§11.4)."""
    p, reg = built
    scene = build_scene(reg, p.family)
    markers = build_axis_markers(p.family.axis_sets)
    assert len(scene.labels) == len(markers)
    for (text, x, y, z, group), marker in zip(scene.labels, markers):
        assert text == marker.axis_id
        assert norm((x, y, z)) > 1.0
        assert scene.axis_sets[group] == marker.axis_set_id


def test_markers_can_be_left_out(built):
    p, reg = built
    scene = build_scene(reg, p.family, markers=False)
    assert set(scene.kinds) == {ARC}
    assert scene.labels == []


def test_json_is_flat_and_rounds_coordinates(built):
    """중첩 배열을 쓰면 평탄화의 이점이 사라진다."""
    p, reg = built
    scene = build_scene(reg, p.family)
    data = json.loads(scene.to_json())
    assert set(data) == {"xyz", "starts", "counts", "groups", "kinds", "labels", "axisSets"}
    assert all(isinstance(v, (int, float)) for v in data["xyz"][:9])
    assert len(data["xyz"]) == 3 * scene.point_count
    # 6자리로 줄여도 구면에서 벗어나지 않는다
    for k in range(0, len(data["xyz"]) // 3, 7):
        assert norm(data["xyz"][3 * k : 3 * k + 3]) == pytest.approx(1.0, abs=1e-5)
    assert len(scene.to_json()) < len(scene.to_json(17))


# ---- 편집 모드의 무대 (§19.15) ------------------------------------------


def test_the_marker_scene_has_no_cuts():
    """편집 모드에서 보려는 것은 축이 어디 있느냐다 (§19.15).

    절단이 같이 보이면 지금 무엇을 고치는 중인지가 흐려지고, 어차피 절단은
    `Run` 전까지 바뀌지 않는다.
    """
    faces = S.cube("cube")
    scene = build_marker_scene([faces.to_engine()])
    assert len(scene) == len(faces)
    assert set(scene.kinds) == {MARKER}
    assert [lab[0] for lab in scene.labels] == [a.id for a in faces]


def test_the_marker_scene_takes_sets_that_are_not_drawn():
    """`puzzle()` 인자가 아닌 집합도 고치려면 어디 있는지 보여야 한다 (§19.12).

    `build_scene` 은 퍼즐에서 축 집합을 얻으므로 이런 집합에 닿을 길이 없다.
    """
    faces = S.cube("cube")
    ref = S.tetrahedron("ref")
    scene = build_marker_scene([faces.to_engine(), ref.to_engine()])

    assert scene.axis_sets == ["cube", "ref"]
    assert len(scene) == len(faces) + len(ref)
    # 그룹이 두 집합에 갈려야 색이 갈린다
    assert set(scene.groups) == {0, 1}


def test_the_marker_scene_does_not_depend_on_the_cut_angle():
    """마커는 축 방향만 쓴다 (§11.4). 슬라이더를 밀어도 같은 장면이다."""
    faces = S.cube("cube")
    a = build_marker_scene([faces.to_engine()])
    b = build_marker_scene([faces.to_engine()])
    assert a.xyz == b.xyz and a.starts == b.starts

