"""Split 연산 테스트. 설계 문서 §6, §17 시나리오."""

import math

import pytest

from cutpattern.engine.axes import Axis, AxisSet, PuzzleFamily
from cutpattern.engine.operations import (
    SplitByAxis,
        Turn,
    evaluate,
)
from cutpattern.geometry.angular_coverage import TAU, total_length


FACE_NORMALS = [
    ("U", (0, 1, 0)),
    ("D", (0, -1, 0)),
    ("R", (1, 0, 0)),
    ("L", (-1, 0, 0)),
    ("F", (0, 0, 1)),
    ("B", (0, 0, -1)),
]

ALL_FACE_SPLITS = tuple(SplitByAxis(i) for i in ("R", "L", "U", "D", "F", "B"))


def face_family(operations=ALL_FACE_SPLITS) -> PuzzleFamily:
    faces = AxisSet(
        id="faces",
        cut_angle_input="faces",
        axes=tuple(Axis.make(i, n, (90.0, -90.0, 180.0)) for i, n in FACE_NORMALS),
    )
    return PuzzleFamily(axis_sets=(faces,), operations=tuple(operations))


def test_3x3x3_split_makes_six_circles():
    reg, log = evaluate(face_family(), {"faces": 54.7356})
    assert len(reg) == 6
    assert all(bc.is_complete for bc in reg)
    assert all(total_length(r.added) == pytest.approx(TAU) for r in log)


def test_2x2x2_split_makes_three_circles():
    reg, log = evaluate(face_family(), {"faces": 90.0})
    assert len(reg) == 3
    assert all(bc.is_complete for bc in reg)
    # 마주보는 축의 두 번째 것은 새로 추가하는 구간이 없다
    assert [total_length(r.added) > 1e-9 for r in log] == [True, False] * 3


def test_repeating_same_split_changes_nothing():
    """같은 split 을 반복 적용해도 결과가 변하지 않는다 (§17)."""
    fam = face_family((*ALL_FACE_SPLITS, *ALL_FACE_SPLITS))
    reg, log = evaluate(fam, {"faces": 54.7356})
    assert len(reg) == 6
    second_pass = log[6:]
    assert all(total_length(r.added) == pytest.approx(0.0) for r in second_pass)


def test_split_by_axis_targets_single_axis():
    fam = face_family((SplitByAxis("R"),))
    reg, log = evaluate(fam, {"faces": 54.7356})
    assert len(reg) == 1
    assert len(log) == 1
    assert log[0].axis_id == "R"


def test_angle_slider_roundtrip_is_exact():
    """각도를 왕복해도 원래 상태로 정확히 복귀한다 (§17)."""
    fam = face_family()

    def snapshot(deg):
        reg, _ = evaluate(fam, {"faces": deg})
        return sorted(
            (round(float(bc.circle.h), 12), len(bc.coverage), round(total_length(bc.coverage), 12))
            for bc in reg
        )

    start = snapshot(54.7356)
    for deg in (20.0, 90.0, 150.0, 179.0, 30.0):
        snapshot(deg)
    assert snapshot(54.7356) == start


@pytest.mark.parametrize("deg", [0.01, 0.5, 90.0, 179.5, 179.99])
def test_slider_range_never_produces_nan(deg):
    reg, log = evaluate(face_family(), {"faces": deg})
    for bc in reg:
        assert math.isfinite(bc.circle.h)
        assert math.isfinite(bc.circle.r)
        assert all(math.isfinite(x) for span in bc.coverage for x in span)


def test_unknown_operation_is_rejected():
    """알 수 없는 연산을 조용히 추측하지 않는다 (§9.4)."""
    fam = PuzzleFamily(axis_sets=face_family().axis_sets, operations=("nonsense",))
    with pytest.raises(TypeError):
        evaluate(fam, {"faces": 54.7356})


def test_split_records_provenance():
    """어느 연산이 만든 호인지 남는다 (§5, 단계 2)."""
    reg, _ = evaluate(face_family(), {"faces": 54.7356})
    for bc in reg:
        for span in bc.spans:
            assert span.provenance.kind == "split"
            # split(집합) 은 축 단위 연산으로 펼쳐지므로 축마다 op_index 가 다르다
            assert span.provenance.op_index in range(6)
            assert span.provenance.axis_id in {a.id for a in face_family().axis_sets[0].axes}
