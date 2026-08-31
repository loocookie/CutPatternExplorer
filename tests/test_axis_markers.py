"""축 마커와 축 집합 토글. 설계 문서 §11, §15.

두 부분이다.

- `render/markers` — 렌더러 비의존. 마커가 registry 를 거치지 않는다는 것이
  핵심이다. 거치면 `total_arc_length` 가 오염되고 §7.1 회전 합법성이 달라진다
- `vpython_view` — 토글과 라벨 앞뒤 판정. vpython 을 스텁으로 갈아 끼워
  창을 띄우지 않고 로직만 돌린다
"""

from __future__ import annotations

import math
import sys
import types

import pytest

from cutpattern import solids as S
from cutpattern.dsl import puzzle, split, turned
from cutpattern.geometry.vector import Vec3, norm
from cutpattern.render.markers import MARKER_ANGLE_DEG, build_axis_markers, marker_id

THETA = math.degrees(math.acos(0.45))


def _family():
    faces = S.cube("cube", turns=(45, -45))
    edges = S.rhombic_dodecahedron("edges")
    with puzzle("marked", faces, edges) as p:
        split(faces)
        with turned(faces["c-3"], 45):
            split(faces["c-2"])
    return p.family


# ---- 렌더러 비의존 계층 ------------------------------------------------


def test_one_marker_per_axis_with_the_axis_id_as_label():
    family = _family()
    markers = build_axis_markers(family.axis_sets)
    assert len(markers) == sum(len(a.axes) for a in family.axis_sets) == 18
    labels = {(m.axis_set_id, m.axis_id) for m in markers}
    assert labels == {
        (aset.id, axis.id) for aset in family.axis_sets for axis in aset.axes
    }


def test_marker_points_lie_on_the_unit_sphere_at_the_marker_angle():
    """절단 호와 같은 면 위에 있어야 반투명 구의 깊이 표현을 그대로 받는다."""
    markers = build_axis_markers(_family().axis_sets)
    want = math.cos(math.radians(MARKER_ANGLE_DEG))
    for m in markers:
        for p in m.points:
            assert norm(p) == pytest.approx(1.0, abs=1e-12)
            # 축 방향에서 정확히 MARKER_ANGLE_DEG 만큼 떨어져 있다
            assert Vec3(p) @ m.direction == pytest.approx(want, abs=1e-12)


def test_marker_id_is_stable_across_cut_angles():
    """호 ID 와 달리 절단 각도가 안 섞인다. 렌더 객체 pool 이 유지된다 (§11)."""
    family = _family()
    a = [m.id for m in build_axis_markers(family.axis_sets)]
    b = [m.id for m in build_axis_markers(family.axis_sets)]
    assert a == b
    assert a[0] == marker_id(family.axis_sets[0].id, family.axis_sets[0].axes[0].id)


def test_markers_never_touch_the_registry():
    """마커는 표시 전용이다.

    registry 에 들어가면 total_arc_length 가 오염되고 is_complete 가 바뀌어
    §7.1 회전 합법성 판정이 달라진다. 조용히 틀리는 종류라 못을 박는다.
    """
    from cutpattern.engine.operations import evaluate

    family = _family()
    reg, _log = evaluate(family, {"cube": THETA, "edges": 70.0})
    before = (len(reg), reg.total_arc_length())
    build_axis_markers(family.axis_sets)
    assert (len(reg), reg.total_arc_length()) == before


# ---- 뷰어 로직 (vpython 스텁) ------------------------------------------


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.visible = True

    def clear(self):
        self.pos = []

    def append(self, pts):
        self.pos = list(pts)


class _Vec:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)


class _Scene(_Obj):
    def append_to_caption(self, _text):
        pass


def _stub_vpython(monkeypatch):
    """창을 띄우지 않는 vpython 대역. 만들어진 객체를 모아 둔다."""
    made = {"checkbox": [], "curve": [], "label": []}
    mod = types.ModuleType("vpython")

    def record(kind):
        def make(**kw):
            obj = _Obj(**kw)
            made[kind].append(obj)
            return obj

        return make

    mod.vector = _Vec
    mod.canvas = lambda **kw: _Scene(**{'forward': _Vec(-0.6, -0.4, -1), **kw})
    mod.sphere = lambda **kw: _Obj(**kw)
    mod.curve = record("curve")
    mod.label = record("label")
    mod.checkbox = record("checkbox")
    mod.slider = lambda **kw: _Obj(**kw)
    mod.wtext = lambda **kw: _Obj(**kw)
    mod.color = types.SimpleNamespace(white=_Vec(1, 1, 1))
    mod.rate = lambda _n: None
    monkeypatch.setitem(sys.modules, "vpython", mod)
    return made


@pytest.fixture
def view(monkeypatch):
    made = _stub_vpython(monkeypatch)
    from cutpattern.render.vpython_view import SphereView

    v = SphereView(_family(), {"cube": THETA, "edges": 70.0})
    v._made = made
    return v


def test_viewer_draws_a_marker_and_label_per_axis(view):
    assert len(view._marker_curves) == 18
    assert len(view._marker_labels) == 18
    texts = {lb.text for lb in view._made["label"]}
    assert "c-2" in texts and "e-0" in texts


def test_hiding_a_set_hides_its_arcs_and_markers(view):
    """토글은 그리기만 막는다. 엔진은 그대로 돈다."""
    lit = lambda: sum(1 for c in view._curves.values() if c.visible)
    before = lit()
    assert before > 0

    view._hidden_sets.add("cube")
    view._draw_markers()
    view.rebuild(0.15)

    hidden_markers = [
        view._marker_curves[m.id] for m in view.markers if m.axis_set_id == "cube"
    ]
    assert not any(c.visible for c in hidden_markers)
    assert lit() < before
    assert "숨긴 축 집합: cube" in view.status.text

    view._hidden_sets.discard("cube")
    view._draw_markers()
    view.rebuild(0.15)
    assert lit() == before
    assert "숨긴 축 집합" not in view.status.text


def test_marker_toggle_hides_every_marker_but_keeps_the_arcs(view):
    view._show_markers = False
    view._draw_markers()
    assert not any(c.visible for c in view._marker_curves.values())
    assert not any(lb.visible for lb in view._marker_labels.values())
    assert any(c.visible for c in view._curves.values())


def test_labels_on_the_far_side_of_the_sphere_are_hidden(view):
    """라벨은 2D 빌보드라 구에 가려지지 않는다. 직접 꺼야 한다."""
    view.scene.forward = _Vec(0, 0, -1)  # +z 를 바라본다
    view._update_label_facing(force=True)
    for m in view.markers:
        toward = m.direction[2] * -1.0
        assert view._marker_labels[m.id].visible == (toward < 0.0)

    # 반대로 돌리면 앞뒤가 뒤집힌다
    view.scene.forward = _Vec(0, 0, 1)
    view._update_label_facing(force=True)
    front = [m for m in view.markers if m.direction[2] < 0]
    assert front and all(view._marker_labels[m.id].visible for m in front)


def test_marker_curves_are_reused_across_rebuilds(view):
    """마커는 절단 각도와 무관하므로 다시 만들지 않는다 (§11 pool)."""
    made_before = len(view._made["curve"])
    ids_before = {k: id(v) for k, v in view._marker_curves.items()}
    view.cut_angles["faces"] = 70.0
    view.rebuild(0.15)
    view._draw_markers()
    assert {k: id(v) for k, v in view._marker_curves.items()} == ids_before
    assert len(view._made["curve"]) >= made_before
