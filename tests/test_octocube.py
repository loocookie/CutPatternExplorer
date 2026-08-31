"""OctoCube Master 시나리오. 설계 문서 §17 시나리오 테스트."""

import math

import numpy as np
import pytest

from cutpattern.engine.operations import evaluate
from examples.octocube_master import CUT_OFFSET, THETA_DEG, build_family

# 정육면체의 12개 모서리 방향
EDGE_NORMALS = [
    np.array(v, dtype=float) / math.sqrt(2.0)
    for v in [
        (1, 1, 0), (1, -1, 0), (-1, 1, 0), (-1, -1, 0),
        (1, 0, 1), (1, 0, -1), (-1, 0, 1), (-1, 0, -1),
        (0, 1, 1), (0, 1, -1), (0, -1, 1), (0, -1, -1),
    ]
]


def _same_plane(n1, h1, n2, h2) -> bool:
    """평면 동일성은 (n, h) 쌍으로 본다.

    (0, .7071, .7071, h=+0.45) 와 (0, -.7071, -.7071, h=+0.45) 는 법선만 반대일
    뿐 서로 **다른** 평면이다. 각각 (y+z)/sqrt2 = +0.45 와 = -0.45 이다.
    같은 평면은 (n, h) == (-n', -h') 일 때뿐이다 (§4.3).
    """
    n2 = np.asarray(n2, dtype=float)
    if np.allclose(n1, n2, atol=1e-9) and abs(h1 - h2) < 1e-9:
        return True
    return np.allclose(n1, -n2, atol=1e-9) and abs(h1 + h2) < 1e-9


def _is_face_plane(bc, face_normals) -> bool:
    return any(_same_plane(bc.circle.n, bc.circle.h, f, CUT_OFFSET) for f in face_normals)


@pytest.fixture(scope="module")
def octo():
    family = build_family()
    reg, log = evaluate(family, {"cube": THETA_DEG})  # on_illegal="raise"
    return family, reg, log


def test_every_turn_is_legal(octo):
    """37개 연산이 불법 회전 없이 완주해야 한다. evaluate 가 기본으로 raise 한다."""
    _family, _reg, log = octo
    from cutpattern.engine.operations import Truncated

    assert not any(isinstance(r, Truncated) for r in log)


def test_face_circles_are_restored_complete(octo):
    """각 블록이 X 를 -45 로 되돌리므로 여섯 면 원은 전부 완전해야 한다."""
    family, reg, _log = octo
    for axis in family.axis_sets[0].axes:
        hit = reg.find(axis.normal, CUT_OFFSET)
        assert hit is not None
        assert hit[0].is_complete, f"{axis.id} 원이 완전하지 않다"


def test_new_boundaries_are_the_twelve_edge_planes(octo):
    """새로 생기는 경계는 정확히 정육면체 12개 모서리 방향 평면이다."""
    family, reg, _log = octo
    face_normals = [a.normal for a in family.axis_sets[0].axes]
    new = [bc for bc in reg.non_empty() if not _is_face_plane(bc, face_normals)]
    assert len(new) == 12
    # 모서리 방향 6개 x offset 부호 2개 = 평면 12개
    for bc in new:
        assert bc.circle.h == pytest.approx(CUT_OFFSET)
        assert any(_same_plane(bc.circle.n, bc.circle.h, e, CUT_OFFSET) for e in EDGE_NORMALS)
    for i, bc in enumerate(new):
        for other in new[i + 1 :]:
            assert not _same_plane(bc.circle.n, bc.circle.h, other.circle.n, other.circle.h)


def test_edge_circles_share_one_coverage_length(octo):
    """대칭이므로 12개 모서리 원의 덮인 길이가 모두 같아야 한다."""
    family, reg, _log = octo
    face_normals = [a.normal for a in family.axis_sets[0].axes]
    lengths = [
        bc.spans.total_length()
        for bc in reg.non_empty()
        if not _is_face_plane(bc, face_normals)
    ]
    assert len(lengths) == 12
    assert lengths == pytest.approx([lengths[0]] * 12)
    assert 0.0 < lengths[0] < 2.0 * math.pi  # 완전한 원은 아니다


def test_total_arc_length_decomposes(octo):
    _family, reg, _log = octo
    edge_len = min(bc.spans.total_length() for bc in reg.non_empty())
    assert reg.total_arc_length() == pytest.approx(6 * 2 * math.pi + 12 * edge_len)


def test_all_arcs_lie_on_the_unit_sphere(octo):
    _family, reg, _log = octo
    for bc in reg.non_empty():
        for span in bc.spans:
            for t in np.linspace(span.t0, span.t1, 4):
                p = bc.circle.point(t)
                assert float(np.linalg.norm(p)) == pytest.approx(1.0, abs=1e-12)
                assert float(p @ bc.circle.n) == pytest.approx(bc.circle.h, abs=1e-12)


def test_result_is_deterministic():
    family = build_family()
    a, _ = evaluate(family, {"cube": THETA_DEG})
    b, _ = evaluate(family, {"cube": THETA_DEG})
    key = lambda reg: sorted(
        (tuple(np.round(bc.circle.n, 9)), round(bc.circle.h, 9), round(bc.spans.total_length(), 9))
        for bc in reg.non_empty()
    )
    assert key(a) == key(b)


@pytest.mark.parametrize("deg", [30.0, 50.0, THETA_DEG, 75.0, 89.0])
def test_slider_sweep_stays_legal_and_finite(deg):
    """절단 각도를 바꿔도 회전이 계속 합법이고 NaN 이 없어야 한다."""
    reg, _ = evaluate(build_family(), {"cube": deg})
    for bc in reg.non_empty():
        assert math.isfinite(bc.circle.h) and math.isfinite(bc.circle.r)
        assert all(math.isfinite(x) for s in bc.spans for x in s.as_tuple())


# ---- 평가 중 각도 변경 --------------------------------------------------


class _MutatingAngles(dict):
    """조회할 때마다 값이 바뀌는 dict. UI 위젯 콜백이 별도 스레드에서 와서
    평가 도중 각도를 바꾸는 상황을 재현한다."""

    def __init__(self, start: float, delta: float) -> None:
        super().__init__({"cube": start})
        self.delta = delta
        self.reads = 0

    def __getitem__(self, key):
        value = super().__getitem__(key)
        self.reads += 1
        super().__setitem__(key, value + self.delta)
        return value


@pytest.mark.parametrize("delta", [1e-6, 1e-3, 0.05, 5.0])
def test_evaluate_snapshots_cut_angles(delta):
    """평가 도중 호출자가 각도를 바꿔도 한 번의 평가는 일관돼야 한다.

    스냅샷이 없으면 앞 연산은 theta1 로 split 하고 뒤 Turn 은 theta2 의 경계원을
    찾게 되어, 합법인 회전이 불법으로 판정된다.
    """
    from cutpattern.engine.operations import Truncated

    angles = _MutatingAngles(THETA_DEG, delta)
    reg, log = evaluate(build_family(), angles, on_illegal="truncate")
    assert not any(isinstance(r, Truncated) for r in log)
    assert angles.reads == 0  # 진입 시 한 번 복사하고 다시 읽지 않는다

    baseline, _ = evaluate(build_family(), {"cube": THETA_DEG})
    assert reg.total_arc_length() == pytest.approx(baseline.total_arc_length())
