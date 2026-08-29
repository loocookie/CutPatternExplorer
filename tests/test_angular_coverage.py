"""각도 구간 연산 테스트. 설계 문서 §17 기하 단위 테스트."""

import math

import pytest

from cutpattern.geometry.angular_coverage import (
    TAU,
    contains,
    difference,
    empty,
    full,
    intersection,
    is_full,
    make_span,
    normalize_spans,
    reflect,
    shift,
    total_length,
    union,
    wrap_angle,
)


def test_full_is_full():
    assert is_full(full())
    assert not is_full(empty())
    assert not is_full([(0.0, TAU - 0.5)])


def test_seam_adjacent_spans_merge_to_full():
    assert is_full([(0.0, 1.0), (1.0, TAU)])
    assert is_full([(1.0, TAU), (0.0, 1.0)])


def test_wrap_crossing_span_decomposed():
    # 5.0 에서 시작해 길이 2.0 -> seam 을 넘는다
    spans = make_span(5.0, 2.0)
    assert len(spans) == 2
    assert total_length(spans) == pytest.approx(2.0)
    assert all(0.0 <= s < e <= TAU for s, e in spans)


def test_difference_preserves_length():
    d = difference(full(), [(1.0, 2.0)])
    assert total_length(d) == pytest.approx(TAU - 1.0)
    assert not is_full(d)


def test_difference_across_seam():
    """0/2pi 를 가로지르는 구간을 빼도 정확해야 한다."""
    removed = make_span(6.0, 1.0)  # 6.0 -> 6.283.. -> 0.716..
    d = difference(full(), removed)
    assert total_length(d) == pytest.approx(TAU - 1.0)
    assert not contains(d, 6.1)
    assert not contains(d, 0.3)
    assert contains(d, 3.0)


def test_union_idempotent():
    a = [(0.5, 1.5), (3.0, 4.0)]
    assert normalize_spans(union(a, a)) == normalize_spans(a)


def test_intersection():
    a = [(0.0, 2.0), (3.0, 5.0)]
    b = [(1.0, 3.5)]
    assert intersection(a, b) == [(1.0, 2.0), (3.0, 3.5)]


def test_shift_preserves_length_and_roundtrips():
    a = [(0.5, 1.5), (4.0, 4.2)]
    for delta in (0.3, 3.0, 6.0, -1.0, TAU):
        s = shift(a, delta)
        assert total_length(s) == pytest.approx(total_length(a))
        assert normalize_spans(shift(s, -delta)) == pytest.approx(normalize_spans(a))


def test_shift_full_stays_full():
    assert is_full(shift(full(), 1.234))


def test_reflect_involution():
    a = [(0.5, 1.5)]
    c = 2.0
    assert normalize_spans(reflect(reflect(a, c), c)) == pytest.approx(a)


def test_wrap_angle_range():
    for t in (-10.0, -TAU, -1e-18, 0.0, 1.0, TAU, TAU + 1e-18, 100.0):
        w = wrap_angle(t)
        assert 0.0 <= w < TAU


def test_tiny_spans_dropped():
    assert normalize_spans([(1.0, 1.0 + 1e-15)]) == []
