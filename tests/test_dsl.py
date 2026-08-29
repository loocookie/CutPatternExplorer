"""내장 DSL 테스트. 설계 문서 §9 대체."""

import math

import pytest

from cutpattern import solids as S
from cutpattern.dsl import (
    AxisSet,
    angle_between,
    at_angle,
    puzzle,
    split,
    turn,
    turned,
)
from cutpattern.engine.operations import RollbackTurns, SplitByAxis, Turn

# 축 id 는 방향을 말해주지 않는다 (`c0`..`c5`). 방향을 박은 id 를 두면
# axisops.rotate 한 번에 거짓말이 되므로 (§2.2), 테스트에서 부를 이름을 여기서
# 묶는다. 방향은 S.cube() 를 갓 만든 상태 기준이다.
R, L = "c2", "c4"   # +x, -x
U, D = "c3", "c1"   # +y, -y
F, B = "c0", "c5"   # +z, -z



# ---- 축 집합 -----------------------------------------------------------


def test_at_angle_covers_perpendicular_opposite_and_self():
    """수직/반대/자기 자신이 전부 at_angle 의 특수한 경우다. 별도 함수는 없다."""
    faces = S.cube("faces")
    assert {a.id for a in at_angle(faces[U], 90, faces)} == {R, L, F, B}
    assert [a.id for a in at_angle(faces[U], 180, faces)] == [D]
    assert [a.id for a in at_angle(faces[U], 0, faces)] == [U]
    assert at_angle(faces[U], 45, faces) == []


def test_at_angle_accepts_axis_objects_and_ids():
    faces = S.cube("faces")
    assert {a.id for a in at_angle(faces[R], 90, faces)} == {U, D, F, B}


def test_at_angle_on_non_cube_set():
    """모서리축처럼 60/90/120/180 이 섞인 집합에서도 각으로 고를 수 있다."""
    edges = S.rhombic_dodecahedron("edges")
    ru = edges["rd6"]  # +x+y 방향
    assert at_angle(ru, 0, edges) == [ru]
    assert [a.id for a in at_angle(ru, 180, edges)] == ["rd4"]  # rd6 의 반대편
    assert len(at_angle(ru, 60, edges)) > 0


def test_angle_to_reports_degrees():
    faces = S.cube("faces")
    assert angle_between(faces[U], faces[R]) == pytest.approx(90.0)
    assert angle_between(faces[U], faces[D]) == pytest.approx(180.0)
    assert angle_between(faces[U], faces[U]) == pytest.approx(0.0)


def test_duplicate_axis_id_is_rejected():
    s = AxisSet("s")
    s.add("A", (1, 0, 0))
    with pytest.raises(ValueError, match="중복"):
        s.add("A", (0, 1, 0))


def test_dot_access_raises_attribute_error_for_unknown_axis():
    faces = S.cube("faces")
    with pytest.raises(AttributeError):
        faces.Nope


# ---- 프로그램 기록 -----------------------------------------------------


def test_split_and_turn_record_operations():
    faces = S.cube("faces")
    with puzzle("t", faces) as p:
        split(faces)
        split(faces[R])
        turn(faces[U], 45)
    # split(집합) 은 축 단위 연산으로 펼쳐진다. 원시 연산은 SplitByAxis 뿐이다
    assert [type(op) for op in p.operations] == [SplitByAxis] * 7 + [Turn]
    assert [op.axis for op in p.operations[:6]] == [a.id for a in faces]
    assert p.operations[6].axis == R
    assert p.operations[7] == Turn(U, 45.0)


def test_rollback_is_appended_automatically():
    """구성용 회전은 정의 끝에서 자동으로 되돌아간다. 별도 함수가 없다."""
    faces = S.cube("faces")
    with puzzle("t", faces) as p:
        split(faces)
        turn(faces[U], 45)
    assert not any(isinstance(op, RollbackTurns) for op in p.operations)
    assert isinstance(p.family.operations[-1], RollbackTurns)
    assert len(p.family.operations) == len(p.operations) + 1


def test_split_accepts_multiple_targets():
    faces = S.cube("faces")
    with puzzle("t", faces) as p:
        split(*at_angle(faces[U], 90, faces))
    # 순서는 at_angle 이 정한다. 여기서 볼 것은 U 에 수직인 네 면이 다 왔는가다
    assert {op.axis for op in p.operations} == {R, L, F, B}


def test_split_with_no_target_is_rejected():
    faces = S.cube("faces")
    with puzzle("t", faces):
        with pytest.raises(TypeError):
            split()


def test_turned_block_emits_matching_inverse():
    faces = S.cube("faces")
    with puzzle("t", faces) as p:
        with turned(faces[U], 45):
            split(faces[R])
    assert p.operations == (Turn(U, 45.0), SplitByAxis(R), Turn(U, -45.0))


def test_turned_block_closes_even_on_exception():
    faces = S.cube("faces")
    pz = puzzle("t", faces)
    with pytest.raises(RuntimeError, match="boom"):
        with pz:
            with turned(faces[U], 45):
                raise RuntimeError("boom")
    # 예외로 빠져나가도 되돌리기가 기록된다
    assert pz.operations == (Turn(U, 45.0), Turn(U, -45.0))


def test_nested_turned_blocks_unwind_in_reverse():
    faces = S.cube("faces")
    with puzzle("t", faces) as p:
        with turned(faces[U], 45):
            with turned(faces[R], 30):
                split(faces[F])
    assert p.operations == (
        Turn(U, 45.0),
        Turn(R, 30.0),
        SplitByAxis(F),
        Turn(R, -30.0),
        Turn(U, -45.0),
    )


def test_python_control_flow_works():
    """for, def, 컴프리헨션, 조건문이 그냥 동작해야 한다."""
    faces = S.cube("faces")

    def block(x):
        with turned(x, 45):
            split(*at_angle(x, 90, faces))

    with puzzle("t", faces) as p:
        split(faces)
        for x in faces:
            if x.id in (U, R):
                block(x)
    # split(faces) 6개 + 축 2개 x (turn + split 4개 + turn)
    assert len(p.operations) == 6 + 2 * 6


def test_operations_outside_block_are_rejected():
    faces = S.cube("faces")
    with pytest.raises(RuntimeError, match="with puzzle"):
        split(faces)
    with pytest.raises(RuntimeError, match="with puzzle"):
        turn(faces[U], 45)


def test_split_rejects_wrong_target():
    faces = S.cube("faces")
    with puzzle("t", faces):
        with pytest.raises(TypeError):
            split("faces")


def test_turn_rejects_wrong_target():
    faces = S.cube("faces")
    with puzzle("t", faces):
        with pytest.raises(TypeError):
            turn(U, 45)


# ---- 검증 --------------------------------------------------------------


def test_axis_id_collision_across_sets_is_rejected():
    """연산이 축을 이름으로 참조하므로 전 집합에서 유일해야 한다."""
    a = AxisSet("a", axes={"X": (1, 0, 0)})
    b = AxisSet("b", axes={"X": (0, 1, 0)})
    with pytest.raises(ValueError, match="중복"):
        puzzle("t", a, b)


def test_missing_cut_angle_is_reported():
    faces = S.cube("faces")
    with puzzle("t", faces) as p:
        split(faces)
    with pytest.raises(KeyError, match="faces"):
        p.evaluate({})


def test_each_axis_set_gets_its_own_slider():
    """집합 id 가 곧 slider 식별자다. 공유하고 싶으면 merge 한다."""
    a = AxisSet("a", axes={"A1": (1, 0, 0)})
    b = AxisSet("b", axes={"B1": (0, 1, 0)})
    with puzzle("t", a, b) as p:
        split(a)
    assert p.cut_inputs == ("a", "b")
    assert a.cut == "a" and b.cut == "b"


def test_puzzle_requires_at_least_one_axis_set():
    with pytest.raises(ValueError):
        puzzle("t")


# ---- 엔진과의 일치 ------------------------------------------------------


def test_dsl_octocube_matches_the_engine_result():
    """DSL 로 쓴 OctoCube 가 기대한 구조를 그대로 만든다."""
    from examples.octocube_master import THETA_DEG, build

    p = build()
    # split(집합) 6 + 축 6개 x (turn + split 4 + turn)
    assert len(p.operations) == 6 + 6 * 6
    assert len(p.family.operations) == len(p.operations) + 1  # 자동 rollback
    reg, _log = p.evaluate({"faces": THETA_DEG})
    assert len(reg.non_empty()) == 18
    faces = p.axis_sets[0]
    for axis in faces:
        hit = reg.find(axis.normal, math.cos(math.radians(THETA_DEG)))
        assert hit is not None and hit[0].is_complete


def test_balanced_turns_leave_nothing_to_roll_back():
    """turned() 로 짝을 맞춘 회전은 자동 rollback 이 헛일을 하지 않아야 한다."""
    from examples.octocube_master import THETA_DEG, build

    p = build()
    reg, _ = p.evaluate({"faces": THETA_DEG})
    # 되돌릴 회전이 남지 않으므로 빈 carrier 가 하나도 안 남는다.
    #
    # 접합(§7.10) 전에는 30 이었다. 왕복이 매번 도착지 carrier 를 만들고 돌아온
    # 뒤 빈 껍데기로 남겼기 때문이다. 접합은 회전을 실행하지 않으므로 껍데기가
    # 생기지 않는다. len(reg) == len(non_empty) 쪽이 원래 재고 싶던 것이다
    assert len(reg) == len(reg.non_empty()) == 18


def test_two_axis_sets_with_separate_sliders():
    faces = S.cube("faces")
    edges = S.rhombic_dodecahedron("edges")
    with puzzle("t", faces, edges) as p:
        split(faces)
        split(edges)
    reg, _ = p.evaluate({"faces": 54.7356, "edges": 70.0})
    assert len(reg.non_empty()) == 18  # 면 6 + 모서리 12


# ---- split 대상 받는 폭 (§9.2) ----------------------------------------


def _axis_ids(ops):
    return [op.axis for op in (ops if isinstance(ops, list) else [ops])]


def test_split_accepts_sets_axes_lists_and_nesting():
    """축, 축 집합, 그것들의 목록을 중첩까지 받는다.

    질의는 목록을 돌려주고 목록끼리 묶는 일이 흔하다. 그때마다 ``*`` 를 붙이거나
    for 문을 쓰게 하면 저작 계층으로서 값이 떨어진다.
    """
    from cutpattern import solids as S
    from cutpattern.dsl import at_angle, puzzle, split

    cube = S.cube()
    octa = S.octahedron()
    x = cube["c2"]

    cases = {
        "집합": (cube, 6),
        "축": (x, 1),
        "질의 결과": (at_angle(x, 90, cube), 4),
        "집합들의 목록": ([cube, octa], 14),
        "축들의 목록": ([cube["c0"], cube["c1"]], 2),
        "튜플": ((cube["c0"], cube["c1"]), 2),
        "중첩": ([cube["c0"], [at_angle(x, 90, cube), octa]], 13),
        "제너레이터": ((a for a in cube), 6),
    }
    for label, (target, count) in cases.items():
        with puzzle("t", cube, octa):
            ops = split(target)
        assert len(_axis_ids(ops)) == count, label


def test_split_still_takes_several_arguments():
    from cutpattern import solids as S
    from cutpattern.dsl import puzzle, split

    cube = S.cube()
    octa = S.octahedron()
    with puzzle("t", cube, octa):
        ops = split(cube, octa)
    assert len(_axis_ids(ops)) == 14


@pytest.mark.parametrize("target", [(), [], {}, "c0"])
def test_split_rejects_empty_or_non_axis_targets(target):
    """빈 대상은 조용히 넘기지 않는다.

    at_angle(x, 90) 처럼 대상을 빠뜨린 질의가 빈 목록을 주는데, 그대로 통과하면
    완성된 것처럼 보이는 no-op 정의가 남는다.
    """
    from cutpattern import solids as S
    from cutpattern.dsl import puzzle, split

    cube = S.cube()
    with puzzle("t", cube):
        with pytest.raises(TypeError):
            split(target)


def test_queries_reject_a_missing_target_set():
    from cutpattern import solids as S
    from cutpattern.dsl import angles_from, at_angle

    x = S.cube()["c2"]
    with pytest.raises(TypeError, match="축 집합"):
        at_angle(x, 90)
    with pytest.raises(TypeError, match="축 집합"):
        angles_from(x)
