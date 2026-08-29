"""절단 원 테스트. 설계 문서 §4, §17."""

import math

import numpy as np
import pytest

from cutpattern.geometry.spherical_circle import SphericalCircle, transfer_spans
from cutpattern.geometry.angular_coverage import TAU, full, is_full, total_length


@pytest.mark.parametrize("deg", [0.01, 30.0, 60.0, 90.0, 120.0, 179.99])
def test_h_equals_cos_theta(deg):
    c = SphericalCircle.from_axis_angle((0, 1, 0), math.radians(deg))
    assert c.h == pytest.approx(math.cos(math.radians(deg)))
    assert c.r == pytest.approx(math.sin(math.radians(deg)))
    assert math.degrees(c.theta) == pytest.approx(deg)


@pytest.mark.parametrize("normal", [(0, 0, 1), (1, 0, 0), (0, 1, 0), (1, 1, 1), (0.3, -0.9, 0.2)])
def test_points_lie_on_sphere_and_plane(normal):
    c = SphericalCircle.from_axis_angle(normal, math.radians(63.0))
    ts = np.linspace(0.0, TAU, 37)
    pts = c.points(ts)
    assert np.allclose(np.linalg.norm(pts, axis=1), 1.0)
    assert np.allclose(np.asarray(pts) @ c.n, c.h)


def test_angle_roundtrip():
    c = SphericalCircle.from_axis_angle((0.3, -0.9, 0.2), math.radians(63.0))
    for t in (0.0, 0.5, 3.0, 5.9):
        assert c.angle_of(c.point(t)) == pytest.approx(t, abs=1e-12)


@pytest.mark.parametrize("deg", [0.01, 0.001, 179.99, 179.999])
def test_no_nan_near_poles(deg):
    """극점 근처에서 NaN 이 나오지 않아야 한다 (§14, §17)."""
    c = SphericalCircle.from_axis_angle((0, 0, 1), math.radians(deg))
    pts = c.points(np.linspace(0.0, TAU, 17))
    assert np.isfinite(pts).all()
    assert np.isfinite(c.r)
    assert np.isfinite(c.theta)


def test_degenerate_circle_flagged():
    c = SphericalCircle.from_normal_offset((0, 0, 1), 1.0)
    assert c.is_degenerate()
    assert c.r == pytest.approx(0.0)
    assert np.isfinite(c.points([0.0, 1.0])).all()


def test_h_slightly_out_of_range_does_not_nan():
    """반올림으로 |h| 가 1 을 살짝 넘어도 sqrt 가 NaN 이 되면 안 된다 (§14)."""
    c = SphericalCircle.from_normal_offset((0, 0, 1), 1.0 + 1e-15)
    assert np.isfinite(c.r)
    assert c.r == pytest.approx(0.0)


def test_transfer_to_negated_circle_matches_geometry():
    """(n,h) 와 (-n,-h) 는 같은 원. 각도 좌표 변환이 실제 점과 일치해야 한다 (§4.3)."""
    c = SphericalCircle.from_axis_angle((0, 1, 0), math.radians(60.0))
    neg = c.negated()
    spans = [(0.5, 1.5)]
    moved = transfer_spans(c, neg, spans)
    assert total_length(moved) == pytest.approx(1.0)
    for t in np.linspace(0.5, 1.5, 9):
        t2 = neg.angle_of(c.point(t))
        assert any(s - 1e-9 <= t2 <= e + 1e-9 for s, e in moved)


def test_transfer_roundtrip():
    c = SphericalCircle.from_axis_angle((0.2, 0.4, -0.5), math.radians(75.0))
    neg = c.negated()
    spans = [(0.5, 1.5), (4.0, 4.7)]
    back = transfer_spans(neg, c, transfer_spans(c, neg, spans))
    assert back == pytest.approx(spans)


def test_transfer_full_stays_full():
    c = SphericalCircle.from_axis_angle((0, 1, 0), math.radians(60.0))
    assert is_full(transfer_spans(c, c.negated(), full()))
