"""region 블록 (pCubes Hide) 과 가시성 표시. 설계 문서 §6.3, §7.9."""

import math

import numpy as np
import pytest

from cutpattern import solids as S
from cutpattern.dsl import at_angle, outside, puzzle, region, split, turned
from cutpattern.engine.operations import SplitResult
from cutpattern.geometry.angular_coverage import contains
from cutpattern.geometry.symmetry import rotation_group

CUT_OFFSET = 0.45
THETA_DEG = math.degrees(math.acos(CUT_OFFSET))
TAU = 2.0 * math.pi


def _faces():
    return S.cube()


def _pair(axis, faces):
    return axis, at_angle(axis, 180, faces)[0]


def _evaluate(p):
    keys = {aset.cut_angle_input for aset in p.family.axis_sets}
    return p.evaluate({k: THETA_DEG for k in keys})


def _is_face(n, faces) -> bool:
    return any(
        np.allclose(n, a.normal, atol=1e-9) or np.allclose(n, -a.normal, atol=1e-9)
        for a in faces
    )


def _on_some_cut(reg, point) -> bool:
    for bc in reg.non_empty():
        if abs(float(point @ bc.circle.n) - bc.circle.h) > 1e-7:
            continue
        if contains(bc.coverage, bc.circle.angle_of(point)):
            return True
    return False


def _final_dangling(reg):
    """최종 상태에서 어떤 절단도 지나가지 않는 호 끝점들.

    블록 안에서 매달리는 것은 정상이다 (숨은 재료가 치워져 있다). 블록이 끝나고
    회전이 되돌아온 뒤에도 매달려 있으면 면 한가운데 모서리가 남는다.
    """
    bad = []
    for bc in reg.non_empty():
        cov = bc.coverage
        ends = [t for span in cov for t in span]
        if not ends:
            continue
        wraps = any(abs(t) < 1e-9 for t in ends) and any(
            abs(t - TAU) < 1e-9 for t in ends
        )
        for t in ends:
            if wraps and (abs(t) < 1e-9 or abs(t - TAU) < 1e-9):
                continue
            point = bc.circle.point(t)
            if not any(
                o is not bc and _on_some_cut_one(o, point) for o in reg.non_empty()
            ):
                bad.append((bc.circle.n, t, point))
    return bad


def _on_some_cut_one(bc, point) -> bool:
    if abs(float(point @ bc.circle.n) - bc.circle.h) > 1e-7:
        return False
    return contains(bc.coverage, bc.circle.angle_of(point))


# ---- 표시 -------------------------------------------------------------


def test_region_tags_outside_spans_hidden_and_exit_clears():
    faces = _faces()
    x, xm = _pair(faces["c2"], faces)
    with puzzle("tag", faces) as p:
        split(faces)
        with region(outside(x), outside(xm)):
            split(faces)
    reg, _log = _evaluate(p)
    # 블록이 끝났으므로 숨은 호가 하나도 남지 않는다
    assert not [s for bc in reg.circles for s in bc.spans if not s.visible]


def test_hidden_spans_do_not_move_with_a_turn():
    """숨은 호는 회전에 참여하지 않는다.

    이것이 기하 영역으로 대신할 수 없는 부분이다. 회전이 보이는 재료를 숨은
    재료 위로 옮기면 위치만으로는 둘을 구분할 수 없다.
    """
    faces = _faces()
    x, xm = _pair(faces["c2"], faces)
    z = faces["c0"]
    with puzzle("hidden-stays", faces) as p:
        split(faces)
        with region(outside(x), outside(xm)):
            with turned(z, 45):
                pass
    reg, _log = _evaluate(p)
    # 왕복이므로 처음 상태로 정확히 돌아온다
    assert reg.total_arc_length() == pytest.approx(6 * TAU, abs=1e-9)
    assert all(bc.is_complete for bc in reg.non_empty())


def test_turn_in_region_round_trip_is_exact():
    faces = _faces()
    x, xm = _pair(faces["c2"], faces)
    z, zm = _pair(faces["c0"], faces)
    with puzzle("round-trip", faces) as p:
        split(faces)
        with region(outside(x), outside(xm)):
            with turned(z, 45):
                with turned(zm, -45):
                    pass
    reg, _log = _evaluate(p)
    assert reg.total_arc_length() == pytest.approx(6 * TAU, abs=1e-9)
    assert len(reg.non_empty()) == 6


# ---- split 범위 -------------------------------------------------------


def test_split_in_region_ignores_hidden_coverage():
    """숨은 호는 새 절단을 막지 않는다.

    숨은 재료는 치워져 있으므로 그 자리에도 잘라야 한다. 막으면 새 절단이
    보이는 재료 한가운데서 끝나 매달린 모서리가 된다 (§6.3).
    """
    faces = _faces()
    x, xm = _pair(faces["c2"], faces)
    z, zm = _pair(faces["c0"], faces)
    with puzzle("visible-only", faces) as p:
        split(faces)
        with region(outside(x), outside(xm)):
            with turned(z, 45):
                with turned(zm, -45):
                    split(faces)
    reg, log = _evaluate(p)
    added = [r for r in log if isinstance(r, SplitResult) and r.added]
    assert added, "영역 안에서 새로 잘린 것이 있어야 한다"
    assert not _final_dangling(reg)


def test_region_split_stays_inside_the_region():
    """영역이 실제로 절단을 제한한다.

    같은 구성을 영역 없이 하면 절단이 더 많이 생긴다.
    """

    def build(use_region: bool):
        faces = _faces()
        x, xm = _pair(faces["c2"], faces)
        z, zm = _pair(faces["c0"], faces)
        with puzzle("cmp", faces) as p:
            split(faces)
            if use_region:
                with region(outside(x), outside(xm)):
                    with turned(z, 45):
                        with turned(zm, -45):
                            split(faces)
            else:
                with turned(z, 45):
                    with turned(zm, -45):
                        split(faces)
        return _evaluate(p)[0]

    limited = build(True).total_arc_length()
    unlimited = build(False).total_arc_length()
    assert limited < unlimited


# ---- OctoCube Master (Hide 판) ----------------------------------------


@pytest.fixture(scope="module")
def octo_hide():
    from examples.octocube_hide import build

    p = build()
    return p.evaluate({"cube": THETA_DEG})[0]


def test_octocube_hide_faces_are_intact(octo_hide):
    faces = S.cube()
    for axis in faces:
        bc, _ = octo_hide.find(axis.normal, CUT_OFFSET)
        assert bc.is_complete


def test_octocube_hide_has_no_dangling_cut(octo_hide):
    assert not _final_dangling(octo_hide)


def test_octocube_hide_new_boundaries_are_edge_planes(octo_hide):
    faces = list(S.cube())
    new = [b for b in octo_hide.non_empty() if not _is_face(b.circle.n, faces)]
    assert len(new) == 12
    for bc in new:
        comps = sorted(abs(round(float(c), 4)) for c in bc.circle.n)
        assert comps == [0.0, 0.7071, 0.7071]
    lengths = {round(b.spans.total_length(), 6) for b in new}
    assert len(lengths) == 1


def test_octocube_hide_is_chiral_tetrahedral(octo_hide):
    """세 매크로의 (숨기는 축, 도는 축) 짝이 3-순환이라 T 대칭까지만 간다.

    회전 방향도 둘 다 같은 부호이므로 거울 대칭이 아니다. 영역 없는 판은
    구면 전체를 자르므로 O 대칭이 된다 (test_octocube.py).
    """
    points = [
        octo_hide.circles[i].circle.point(t0 + (t1 - t0) * k / 8)
        for i in range(len(octo_hide))
        for t0, t1 in octo_hide.circles[i].coverage
        for k in range(1, 8)
    ]
    assert all(
        _on_some_cut(octo_hide, g @ q) for g in rotation_group("T") for q in points
    )
    assert not all(
        _on_some_cut(octo_hide, g @ q) for g in rotation_group("O") for q in points
    )


def test_octocube_hide_cuts_less_than_the_unrestricted_version(octo_hide):
    from examples.octocube_master import build_family

    from cutpattern.engine.operations import evaluate

    plain, _ = evaluate(build_family(), {"faces": THETA_DEG})
    assert octo_hide.total_arc_length() < plain.total_arc_length()


# ---- 짝 맞추기 --------------------------------------------------------


def test_unbalanced_turn_in_region_is_rejected():
    faces = _faces()
    x, xm = _pair(faces["c2"], faces)
    z = faces["c0"]
    from cutpattern.dsl import turn as turn_op

    with puzzle("unbalanced", faces) as p:
        split(faces)
        with region(outside(x), outside(xm)):
            turn_op(z, 45)
    with pytest.raises(ValueError, match="되돌려지지"):
        _evaluate(p)


@pytest.mark.parametrize("theta", [30.0, 45.0, 50.0, 63.2563, 70.0, 85.0])
def test_octocube_hide_survives_the_whole_slider_range(theta):
    """slider 를 어디에 두어도 매달린 절단이 남지 않는다.

    45도 이하에서는 회전한 영역이 cap 안의 면 원에 닿지 않아 새 절단이 없다.
    """
    from examples.octocube_hide import build

    reg, _log = build().evaluate({"cube": theta})
    assert not _final_dangling(reg)
    assert not [s for bc in reg.circles for s in bc.spans if not s.visible]


def test_moved_arc_is_not_swallowed_by_hidden_coverage():
    """회전으로 옮긴 호는 숨은 호가 있는 자리에도 들어가야 한다.

    막히면 옮긴 호가 사라지고, 되돌릴 때 돌아오지 않아 **원래 carrier 가 뚫린다**.
    한 블록 안에서는 드러나지 않는다. 앞선 블록이 만들어 둔 부분 carrier 위로
    회전이 겹칠 때 나온다 (§7.9).

    최소 재현은 정십이면체다. 같은 축(d2)을 도는 매크로 둘을, 숨기는 축만
    바꿔 이어서 돌린다.
    """
    from cutpattern import solids as S

    theta = 36.0
    offset = math.cos(math.radians(theta))
    faces = S.dodecahedron()
    opp = {a.id: at_angle(a, 180, faces)[0] for a in faces}
    by_id = {a.id: a for a in faces}

    with puzzle("swallow", faces) as p:
        split(faces)
        for hide, spin in (("d0", "d2"), ("d1", "d2")):
            with region(outside(by_id[hide]), outside(opp[hide])):
                with turned(by_id[spin], 36.0):
                    with turned(opp[spin], -36.0):
                        split(faces)
    reg, _log = p.evaluate({"dodeca": theta})
    for axis in faces:
        bc, _orient = reg.find(axis.normal, offset)
        assert bc.is_complete, f"{axis.id} 면 원이 뚫렸다"


# ---- 경계가 실제 절단인가 (§6.3) --------------------------------------


def test_region_with_an_uncut_boundary_is_rejected():
    """경계축을 자르지 않은 채 region 을 잡으면 거부한다.

    영역 제한 split 은 경계에서 잘린다. 그 자리에 절단이 없으면 잘린 끝이
    아무 데도 닿지 않아 면 한가운데 매달린 모서리가 남는다. 블록이 끝나고
    회전이 되돌아온 뒤에도 남는 진짜 결함이라, 사후 진단이 아니라 사전 판정으로
    막는다. Turn 합법성(§7.1)과 같은 성격이다.
    """
    from cutpattern.engine.operations import UncutBoundaryError

    faces = _faces()
    x, xm = _pair(faces["c2"], faces)
    z = faces["c0"]
    with puzzle("uncut", faces) as p:
        split(z)  # 경계로 쓸 x 를 자르지 않았다
        with region(outside(x), outside(xm)):
            split(at_angle(z, 90, faces))
    with pytest.raises(UncutBoundaryError, match="c2"):
        _evaluate(p)


def test_splitting_the_boundary_first_makes_it_legal():
    """경계를 먼저 split 하면 통과하고 매달림도 남지 않는다."""
    faces = _faces()
    x, xm = _pair(faces["c2"], faces)
    z = faces["c0"]
    with puzzle("cut-first", faces) as p:
        split(z, x, xm)
        with region(outside(x), outside(xm)):
            split(at_angle(z, 90, faces))
    reg, _log = _evaluate(p)
    assert not _final_dangling(reg)


def test_boundary_check_only_asks_for_the_part_that_cuts_the_cell():
    """한 경계가 셀을 가르는 부분만 요구한다.

    원 전체를 요구하면 회전을 거쳐 일부만 남은 경계가 멀쩡한데도 거부된다.
    OctoCube Hide 가 바로 그 경우다.
    """
    from examples.octocube_hide import build

    reg, _log = build().evaluate({"cube": THETA_DEG})
    assert not _final_dangling(reg)


def test_uncut_boundary_follows_the_on_illegal_policy():
    """경계 미절단도 truncate 정책을 탄다 (§6.3, §13.2).

    경계가 절단인지는 cut angle 의 함수다. 아래 정의는 theta <= 45 에서는
    합법이고 그 위에서는 R 원의 U cap 쪽이 회전으로 딴 carrier 에 가 있어
    경계가 뚫린다. 슬라이더를 미는 것만으로 넘는 선이다.

    여기서 예외를 그대로 올리면 뷰어의 재생성 루프가 죽고, 각도를 되돌려도
    복원할 앱이 남지 않는다. 불법 Turn 과 같은 처리를 해야 한다.
    """
    from cutpattern.dsl import cube_faces, turn
    from cutpattern.engine.operations import Truncated, UncutBoundaryError

    def build():
        f = cube_faces("faces", turns=(45, -45, 90, -90, 180))
        with puzzle("uncut-policy", f) as p:
            split(f)
            turn(f.U, 45)
            with region(outside(f.R), outside(f.L)):
                split(f.F, f.B)
        return p

    p = build()

    # 얕은 절단에서는 양쪽 정책 모두 통과한다
    for policy in ("raise", "truncate"):
        _reg, log = p.evaluate({"faces": 40.0}, on_illegal=policy)
        assert not [r for r in log if isinstance(r, Truncated)]

    # 깊어지면 raise 는 올리고
    with pytest.raises(UncutBoundaryError, match="R"):
        p.evaluate({"faces": 63.0}, on_illegal="raise")

    # truncate 는 직전 상태에서 멈추고 기록만 남긴다
    _reg, log = p.evaluate({"faces": 63.0}, on_illegal="truncate")
    trunc = [r for r in log if isinstance(r, Truncated)]
    assert len(trunc) == 1
    assert trunc[0].axis_id == "R"
    assert trunc[0].remaining > 0

    # 슬라이더를 되돌리면 복원된다 (§13.2). 평가가 상태를 들고 있지 않으므로
    # 같은 각도는 항상 같은 결과여야 한다
    reg_back, log_back = p.evaluate({"faces": 40.0}, on_illegal="truncate")
    assert not [r for r in log_back if isinstance(r, Truncated)]
    reg_first, _ = build().evaluate({"faces": 40.0}, on_illegal="truncate")
    assert reg_back.total_arc_length() == pytest.approx(
        reg_first.total_arc_length(), abs=1e-12
    )
