"""cap 분류 테스트. 설계 문서 §7.2, §17."""

import math

import numpy as np
import pytest

from cutpattern.geometry.angular_coverage import TAU
from cutpattern.geometry.classify import (
    FIXED,
    MIXED,
    MOVING,
    circle_terms,
    classify_carrier,
    classify_span,
    split_span_by_cap,
    straddle_roots,
)
from cutpattern.geometry.spherical_circle import SphericalCircle

A = (0.0, 1.0, 0.0)


def test_amplitude_formula():
    c = SphericalCircle.from_axis_angle((1, 0, 0), math.radians(60.0))
    ct = circle_terms(c, A)
    an = float(np.asarray(A) @ c.n)
    assert ct.an == pytest.approx(an)
    assert ct.m == pytest.approx(c.h * an)
    expected_s = math.sqrt(1 - c.h**2) * math.sqrt(1 - an**2)
    assert ct.s == pytest.approx(expected_s)


def test_value_matches_direct_dot_product():
    c = SphericalCircle.from_axis_angle((0.3, 0.5, -0.8), math.radians(70.0))
    ct = circle_terms(c, A)
    for t in np.linspace(0.0, TAU, 13):
        assert ct.value(t) == pytest.approx(float(np.asarray(A) @ c.point(t)))


def test_coaxial_carrier_has_zero_amplitude():
    """회전축과 동축인 carrier 는 s = 0. Turn 마다 반드시 나온다 (§7.2 1단계)."""
    c = SphericalCircle.from_axis_angle((0, 1, 0), math.radians(54.7356))
    ct = circle_terms(c, A)
    assert ct.is_coaxial
    assert ct.s == pytest.approx(0.0)


def test_antiparallel_carrier_is_also_coaxial():
    """D 축처럼 법선이 회전축과 반대여도 동축이다."""
    c = SphericalCircle.from_axis_angle((0, -1, 0), math.radians(54.7356))
    ct = circle_terms(c, A)
    assert ct.is_coaxial
    d = math.cos(math.radians(54.7356))
    assert classify_carrier(c, A, d) == FIXED


def test_coaxial_never_divides_by_zero():
    """s = 0 인데 교점을 풀면 0 으로 나누기가 된다. 빈 목록이어야 한다 (§7.3)."""
    c = SphericalCircle.from_axis_angle((0, 1, 0), math.radians(54.7356))
    assert straddle_roots(c, A, 0.5) == []


@pytest.mark.parametrize("tilt_deg", [1e-3, 1e-5, 1e-7])
def test_near_coaxial_produces_no_nan(tilt_deg):
    """준동축에서 (d-m)/s 가 정의역을 벗어나 NaN 이 되면 안 된다 (§7.2)."""
    tilt = math.radians(tilt_deg)
    n = (math.sin(tilt), math.cos(tilt), 0.0)
    c = SphericalCircle.from_axis_angle(n, math.radians(54.7356))
    d = math.cos(math.radians(54.7356))
    ct = circle_terms(c, A)
    assert math.isfinite(ct.s)
    for r in straddle_roots(c, A, d):
        assert math.isfinite(r)
    assert classify_carrier(c, A, d) in (MOVING, FIXED, MIXED)


def test_carrier_entirely_inside_cap():
    c = SphericalCircle.from_axis_angle((0, 1, 0), math.radians(10.0))
    assert classify_carrier(c, A, math.cos(math.radians(80.0))) == MOVING


def test_carrier_entirely_outside_cap():
    c = SphericalCircle.from_axis_angle((0, 1, 0), math.radians(170.0))
    assert classify_carrier(c, A, math.cos(math.radians(30.0))) == FIXED


def test_carrier_straddling_is_mixed():
    c = SphericalCircle.from_axis_angle((1, 0, 0), math.radians(54.7356))
    assert classify_carrier(c, A, math.cos(math.radians(54.7356))) == MIXED


def test_straddle_roots_are_on_the_cap_boundary():
    c = SphericalCircle.from_axis_angle((1, 0, 0), math.radians(54.7356))
    d = math.cos(math.radians(54.7356))
    roots = straddle_roots(c, A, d)
    assert len(roots) == 2
    for r in roots:
        assert float(np.asarray(A) @ c.point(r)) == pytest.approx(d)


def test_split_span_preserves_total_length():
    c = SphericalCircle.from_axis_angle((1, 0, 0), math.radians(54.7356))
    d = math.cos(math.radians(54.7356))
    pieces = split_span_by_cap(c, A, d, 0.0, TAU)
    assert sum(e - s for s, e, _ in pieces) == pytest.approx(TAU)
    assert any(mv for _, _, mv in pieces)
    assert any(not mv for _, _, mv in pieces)


def test_split_span_moving_length_matches_geometry():
    """R 원이 U cap 안에 갖는 호 길이는 2*acos(h/r) 이다."""
    theta = math.radians(54.7356)
    c = SphericalCircle.from_axis_angle((1, 0, 0), theta)
    d = math.cos(theta)
    pieces = split_span_by_cap(c, A, d, 0.0, TAU)
    moving = sum(e - s for s, e, mv in pieces if mv)
    expected = 2.0 * math.acos(d / c.r)
    assert moving == pytest.approx(expected)


def test_span_on_cap_boundary_is_fixed():
    """경계에 얹힌 호는 움직이지 않는다 (§7.2 0단계, > d 규칙)."""
    theta = math.radians(54.7356)
    c = SphericalCircle.from_axis_angle((0, 1, 0), theta)
    assert classify_span(c, A, math.cos(theta), 0.0, TAU) == FIXED
