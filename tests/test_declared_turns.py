"""선언된 회전각. 설계 문서 §7.11.

`turns=` 는 **보조 목록이 아니라 명세**다. 적어 두면 그 각으로만 돈다.
비어 있으면 제약이 없다 — 타입을 안 붙인 인자와 같다.

검사는 정적이다. 절단 각도의 함수가 아니므로 `evaluate` 의 on_illegal
정책(§13.2)이 아니라 `Puzzle.check()` 에서 본다.
"""

from __future__ import annotations

import pytest

from cutpattern import solids as S
from cutpattern.dsl import puzzle, split, turn
from cutpattern.engine.turns import available_turns, matches_declared

# 부호 반전에 닫혀 있지 않은 목록. 이런 데서만 cap/outer 차이가 드러난다
ASYMMETRIC = (0, 30, 90, 120, 180, -90, -60)


def _build(turns, angle, outer=False):
    aset = S.cube("c", turns=turns)
    with puzzle("p", aset) as p:
        split(aset)
        turn(list(aset)[0], angle, outer=outer)
    return p


def test_no_declaration_means_no_constraint():
    """안 적었으면 아무 각이나 돈다.

    이것이 아니면 기존 정의 대부분이 깨진다 — examples 의 Turn 89개 중 52개가
    선언이 빈 축에 있다. 타입 주석을 안 붙인 인자와 같은 규약이다.
    """
    _build((), 37.3)
    _build((), 37.3, outer=True)


def test_a_declared_angle_turns():
    _build(ASYMMETRIC, 30)
    _build(ASYMMETRIC, -90)


def test_an_undeclared_angle_is_refused():
    with pytest.raises(ValueError, match="declares turn angles"):
        _build(ASYMMETRIC, 60)


def test_the_message_names_the_axis_and_the_list():
    """거부 메시지가 무엇을 고쳐야 하는지 말해야 한다."""
    with pytest.raises(ValueError) as caught:
        _build(ASYMMETRIC, 60)
    text = str(caught.value)
    assert "'c-0'" in text
    assert "60" in text
    assert "30" in text and "120" in text, "선언 목록을 보여 줘야 한다"


def test_outer_flips_the_sign():
    """**선언은 cap 기준이다** (§7.11).

    cap 을 +t 돌린 상태는 outer 를 -t 돌린 상태와 (구 전체 회전 차이로) 같다.
    그래서 `-60` 을 선언해 두면 outer 60 이 열리고, outer -60 은 막힌다.
    """
    _build(ASYMMETRIC, 60, outer=True)      # -60 이 선언돼 있다
    _build(ASYMMETRIC, 90, outer=True)      # -90 이 선언돼 있다

    with pytest.raises(ValueError, match="an outer turn by -60 needs 60"):
        _build(ASYMMETRIC, -60, outer=True)

    # cap 은 되는데 outer 는 안 되는 각. 비대칭 목록에서만 갈린다
    _build(ASYMMETRIC, 120)
    with pytest.raises(ValueError, match="an outer turn by 120 needs -120"):
        _build(ASYMMETRIC, 120, outer=True)


def test_a_symmetric_list_hides_the_difference():
    """`45, -45, 90, -90, 180` 은 부호 반전에 닫혀 있다.

    mixup_plus 가 이 목록을 쓰기 때문에 cap/outer 차이가 안 드러났다. 이것이
    규칙이 아니라 우연이라는 것을 못 박는다.
    """
    symmetric = (45, -45, 90, -90, 180)
    for angle in symmetric:
        for outer in (False, True):
            _build(symmetric, angle, outer=outer)


def test_angles_are_a_circle():
    """0~360 고리로 본다. -90 과 270 은 같은 각이다."""
    aset = S.cube("c", turns=(-90,))
    axis = list(aset)[0]
    assert matches_declared(axis, 270)
    assert matches_declared(axis, -90)
    assert matches_declared(axis, 630)      # 270 + 360
    assert not matches_declared(axis, 90)


def test_the_check_does_not_depend_on_the_cut_angle():
    """선언은 절단 각도의 함수가 아니다 (§13.2 와 다른 종류다).

    §7.1 회전 합법성은 슬라이더를 밀다 참↔거짓이 오가지만, 선언에 없는 각은
    어느 각도에서도 틀리다. 그래서 evaluate 가 아니라 check() 에서 잡는다.
    """
    p = _build(ASYMMETRIC, 30)
    for theta in (5.0, 40.0, 67.5, 120.0):
        p.evaluate({"c": theta}, on_illegal="truncate")

    # 그리고 거부는 evaluate 를 부르기 전에, 블록을 벗어나는 순간 일어난다
    with pytest.raises(ValueError):
        _build(ASYMMETRIC, 60)


def test_available_turns_flips_declared_angles_for_outer():
    """안내 목록도 같은 규칙을 쓴다 (§7.7, §7.11).

    전에는 outer 와 무관하게 선언을 그대로 얹어서, 비대칭 목록이면 outer 쪽에
    틀린 각을 내놓았다.
    """
    aset = S.cube("c", turns=(30,))
    with puzzle("p", aset) as p:
        split(aset)
    axis = p.family.axis_sets[0].axes[0]

    inner = available_turns(p.family, axis, {"c": 67.5}, outer=False)
    outer = available_turns(p.family, axis, {"c": 67.5}, outer=True)

    assert any(abs(v - 30.0) < 1e-6 for v in inner)
    assert any(abs(v - 330.0) < 1e-6 for v in outer), "선언 30 은 outer 에서 330"
    assert not any(abs(v - 30.0) < 1e-6 for v in outer)


def test_the_existing_examples_all_declare_consistently():
    """지금 저장소의 정의는 이미 이 규칙을 지킨다.

    선언을 한 축이 선언 밖 각으로 도는 경우가 하나도 없다 — 저자들이 이미
    이 필드를 명세로 쓰고 있었다는 증거다.
    """
    import importlib
    import pathlib

    from cutpattern.engine.operations import Turn

    root = pathlib.Path(__file__).resolve().parents[1]
    for path in sorted((root / "examples").glob("*.py")):
        if path.name == "__init__.py":
            continue
        module = importlib.import_module(f"examples.{path.stem}")
        if not hasattr(module, "build"):
            continue
        family = module.build().family     # build() 안에서 check() 가 이미 돈다
        axes = {a.id: a for s in family.axis_sets for a in s.axes}
        for op in family.operations:
            if isinstance(op, Turn):
                assert matches_declared(axes[op.axis], op.angle, op.outer), (
                    path.stem, op.axis, op.angle, op.outer)
