"""provenance span 계층 테스트. 설계 문서 §5, §16 단계 2."""

import pytest

from cutpattern.geometry.angular_coverage import TAU, is_full, total_length
from cutpattern.geometry.span import AngularSpan, Provenance, SpanList

P1 = Provenance(op_index=0, axis_id="U", kind="split")
P2 = Provenance(op_index=1, axis_id="R", kind="turn")


def test_add_returns_only_the_gap():
    sl = SpanList()
    added = sl.add([(0.0, 4.0)], P1)
    assert total_length(added) == pytest.approx(4.0)
    added2 = sl.add([(0.0, TAU)], P2)
    assert total_length(added2) == pytest.approx(TAU - 4.0)
    assert is_full(sl.intervals())


def test_different_provenance_spans_are_not_merged():
    """병합하면 어느 연산이 만든 호인지 사라진다."""
    sl = SpanList()
    sl.add([(0.0, 4.0)], P1)
    sl.add([(0.0, TAU)], P2)
    assert len(sl) == 2
    assert {s.provenance for s in sl} == {P1, P2}
    # 구간 수학 계층에서는 하나로 합쳐 보인다
    assert is_full(sl.intervals())


def test_adding_covered_range_adds_nothing():
    sl = SpanList()
    sl.add([(0.0, TAU)], P1)
    assert sl.add([(1.0, 2.0)], P2) == []
    assert len(sl) == 1


def test_subtract_inherits_provenance():
    from cutpattern.geometry.registry import BoundaryCircle
    from cutpattern.geometry.spherical_circle import SphericalCircle

    bc = BoundaryCircle(index=0, circle=SphericalCircle.from_normal_offset((0, 1, 0), 0.5))
    bc.spans.add([(0.0, TAU)], P1)
    bc.subtract([(1.0, 2.0)])
    assert len(bc.spans) == 2
    assert all(s.provenance == P1 for s in bc.spans)
    assert bc.spans.total_length() == pytest.approx(TAU - 1.0)
    assert not bc.is_complete


def test_with_range_keeps_provenance():
    s = AngularSpan(0.0, 1.0, P1)
    t = s.with_range(0.2, 0.5)
    assert t.provenance is P1
    assert t.length == pytest.approx(0.3)
