"""선언된 방향. 설계 문서 §7.11.

`turns=` 는 **돌 수 있는 양이 아니라 있을 수 있는 방향**이다. 시작이 0 이고,
모든 회전은 축을 선언된 방향 중 하나로 데려가야 한다. 비어 있으면 제약이
없다 — 타입을 안 붙인 인자와 같다.

검사는 정적이다. 절단 각도의 함수가 아니므로 `evaluate` 의 on_illegal
정책(§13.2)이 아니라 `Puzzle.check()` 에서 본다.
"""

from __future__ import annotations

import pytest

from cutpattern import solids as S
from cutpattern.dsl import at_angle, puzzle, split, turn, turned
from cutpattern.engine.turns import available_turns, state_after, state_is_declared

# 22.5 의 배수. 이 목록에는 45 도 0 도 없다 — 그것이 검사를 드러낸다
EIGHTHS = (22.5, 90, 112.5, 180, 202.5, 270, 292.5)


def _build(turns, angle, outer=False):
    aset = S.cube("c", turns=turns)
    with puzzle("p", aset) as p:
        split(aset)
        turn(list(aset)[0], angle, outer=outer)
    return p


def test_no_declaration_means_no_constraint():
    """안 적었으면 어느 방향이든 된다.

    examples 의 Turn 89개 중 52개가 선언이 빈 축에 있다. 타입 주석을 안 붙인
    인자와 같은 규약이다.
    """
    _build((), 37.3)
    _build((), 37.3, outer=True)


def test_a_declared_orientation_is_reached():
    _build(EIGHTHS, 22.5)
    _build(EIGHTHS, 90)
    _build(EIGHTHS, -90)        # 270 으로 간다. 고리다


def test_an_undeclared_orientation_is_refused():
    with pytest.raises(ValueError, match="declared orientations"):
        _build(EIGHTHS, 45)


def test_the_message_says_where_it_landed():
    """무엇을 고쳐야 하는지 말해야 한다. 뜻이 바뀐 필드라 더 그렇다."""
    with pytest.raises(ValueError) as caught:
        _build(EIGHTHS, 45)
    text = str(caught.value)
    assert "'c-0'" in text
    assert "45" in text, "어디에 도착했는지"
    assert "22.5" in text, "선언 목록"
    assert "not the amounts it may turn by" in text, "뜻을 알려 줘야 한다"
    assert "0 is" in text, "0 이 늘 된다는 것"


def test_coming_home_is_always_allowed():
    """**0 은 늘 유효하다.** 이것이 이 규칙의 핵심이다 (§7.11).

    `with turned(x, 22.5)` 는 블록을 나올 때 -22.5 를 낸다. 그것을 변화량으로
    보면 목록에 없어 거부되지만, 실제로는 축을 22.5 에서 **0 으로 되돌리는**
    것이라 완벽히 정상이다. 22.5 의 배수만 선언한 정의가 여기서 죽었다.
    """
    aset = S.cube("c", turns=EIGHTHS)
    with puzzle("p", aset) as p:
        split(aset)
        with turned(list(aset)[0], 22.5):
            split(aset)
    assert p.family is not None


def test_the_users_definition_that_found_this():
    """실제로 이 버그를 드러낸 정의. 22.5 의 배수로 도는 큐브."""
    c1 = S.cube("Cube 1", turns=EIGHTHS)
    rd1 = S.rhombic_dodecahedron("Rhombic Dodecahedron 1")

    def pair(a):
        return (a, at_angle(a, 180, c1)[0])

    with puzzle("Krystian's Cube", c1, rd1) as p:
        split(c1)
        for i in range(4):
            x, y = pair(c1[f"c1-{i}"])
            with turned(x, 22.5):
                with turned(y, 22.5):
                    split(at_angle(x, 90, rd1))
    assert p.family is not None


def test_orientation_accumulates():
    """방향은 쌓인다. 22.5 를 두 번 돌면 45 이고, 45 는 선언에 없다."""
    aset = S.cube("c", turns=EIGHTHS)
    axis = list(aset)[0]
    with pytest.raises(ValueError, match="45"):
        with puzzle("p", aset) as p:
            split(aset)
            turn(axis, 22.5)
            turn(axis, 22.5)


def test_outer_counts_backwards():
    """outer 를 `+t` 도는 것은 cap 을 `-t` 도는 것과 같다 (§2.4)."""
    assert state_after(0.0, 22.5, outer=False) == pytest.approx(22.5)
    assert state_after(0.0, 22.5, outer=True) == pytest.approx(337.5)

    # 292.5 는 선언에 있고 67.5 는 없다
    _build(EIGHTHS, 67.5, outer=True)
    with pytest.raises(ValueError):
        _build(EIGHTHS, 67.5, outer=False)


def test_other_axes_do_not_move_the_state():
    """**자기 회전만 센다** (§7.11).

    다른 축의 회전이 이 축의 재료를 옮기더라도 — 실려 도는 경우까지 —
    방향은 안 바뀐다. 구 전체가 돌아간 것과 같아 상대 방향이 그대로다.
    """
    shell = S.cube("shell")
    rider = S.octahedron("rider", turns=(90, 180, 270))
    with puzzle("p", shell, rider) as p:
        split(shell)
        split(rider)
        # shell 을 아무리 돌려도 rider 의 방향은 0 이다
        turn(list(shell)[0], 37.0)
    assert p.family is not None


def test_orientations_are_a_circle():
    """0~360 고리로 본다. -90 과 270 은 같은 방향이다."""
    aset = S.cube("c", turns=(270,))
    axis = list(aset)[0]
    assert state_is_declared(axis, 270)
    assert state_is_declared(axis, -90)
    assert state_is_declared(axis, 630)     # 270 + 360
    assert state_is_declared(axis, 0)       # 집은 늘 열려 있다
    assert not state_is_declared(axis, 90)


def test_the_check_does_not_depend_on_the_cut_angle():
    """선언은 절단 각도의 함수가 아니다 (§13.2 와 다른 종류다)."""
    p = _build(EIGHTHS, 22.5)
    for theta in (5.0, 40.0, 67.5, 120.0):
        p.evaluate({"c": theta}, on_illegal="truncate")

    with pytest.raises(ValueError):
        _build(EIGHTHS, 45)


def test_available_turns_offers_the_way_to_each_orientation():
    """선언은 방향이고 안내는 회전량이다 (§7.7, §7.11).

    지금 방향에서 선언된 방향으로 가는 차이를 낸다. 집으로 오는 길도 늘 있다.
    """
    aset = S.cube("c", turns=(90,))
    with puzzle("p", aset) as p:
        split(aset)
    axis = p.family.axis_sets[0].axes[0]

    home = available_turns(p.family, axis, {"c": 67.5})
    assert any(abs(v - 90.0) < 1e-6 for v in home), home

    # 90 에 서 있으면 90 으로 가는 회전은 0 이라 안 나오고, 집으로 오는 270 이 나온다
    turned_ = available_turns(p.family, axis, {"c": 67.5}, state=90.0)
    assert any(abs(v - 270.0) < 1e-6 for v in turned_), turned_


def test_the_existing_examples_all_stay_inside_their_declarations():
    """지금 저장소의 정의가 새 규칙을 지키는가.

    `build()` 안에서 `check()` 가 이미 돈다 — 여기 도달하면 통과한 것이다.
    """
    import importlib
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    for path in sorted((root / "examples").glob("*.py")):
        if path.name == "__init__.py":
            continue
        module = importlib.import_module(f"examples.{path.stem}")
        if hasattr(module, "build"):
            assert module.build().family is not None, path.stem
