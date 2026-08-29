"""벡터, 기저, 회전. 설계 문서 §4.2, §7.3."""

from __future__ import annotations

import numpy as np

from ..epsilon import NORMAL_EPS

__all__ = [
    "as_vec",
    "clamp",
    "normalize",
    "orthonormal_basis",
    "rotation_matrix",
]


def as_vec(v) -> np.ndarray:
    """길이 3 float64 배열로 변환."""
    a = np.asarray(v, dtype=np.float64).reshape(3)
    return a


def clamp(x, lo: float = -1.0, hi: float = 1.0):
    """역삼각함수 정의역 보호. 스칼라와 배열 모두 처리 (§14)."""
    return np.clip(x, lo, hi)


def normalize(v) -> np.ndarray:
    a = as_vec(v)
    norm = float(np.linalg.norm(a))
    if norm < NORMAL_EPS:
        raise ValueError("영벡터는 정규화할 수 없다")
    return a / norm


def orthonormal_basis(n) -> tuple[np.ndarray, np.ndarray]:
    """법선 n에 수직인 결정적 정규직교기저 (u, v)를 만든다.

    같은 n에 대해 항상 같은 (u, v)가 나와야 한다. 그래야 carrier가 병합될 때
    각도 좌표 변환량이 0에 가깝게 유지된다.

    (u, v, n)은 오른손계다: u x v = n. 따라서 t가 증가하는 방향은
    +n 쪽에서 볼 때 반시계 방향이다.
    """
    nn = normalize(n)
    # n과 가장 덜 평행한 표준 기저축을 고른다. 동률은 낮은 인덱스.
    e = np.zeros(3)
    e[int(np.argmin(np.abs(nn)))] = 1.0
    u = np.cross(e, nn)
    u /= np.linalg.norm(u)
    v = np.cross(nn, u)
    return u, v


def rotation_matrix(axis, angle: float) -> np.ndarray:
    """axis를 중심으로 angle(라디안)만큼 도는 회전행렬. Rodrigues 공식.

    +axis 쪽에서 볼 때 반시계 방향이 양의 각이다.
    """
    a = normalize(axis)
    ax, ay, az = a
    K = np.array(
        [
            [0.0, -az, ay],
            [az, 0.0, -ax],
            [-ay, ax, 0.0],
        ]
    )
    return np.eye(3) + np.sin(angle) * K + (1.0 - np.cos(angle)) * (K @ K)
