"""벡터, 기저, 회전. 설계 문서 §4.2, §7.3, §12.

numpy 를 쓰지 않는다 (§15). 이 계층이 다루는 것은 길이 3 벡터와 3x3 행렬뿐인데,
그 크기에서는 numpy 배열 하나를 만드는 값이 계산 자체보다 비싸다. 실측으로
`np.cross` 한 함수가 evaluate 누적 시간의 37% 였다. 브라우저(Pyodide)에서는
배열 할당과 C 경계 왕복이 더 비싸므로 격차가 더 벌어진다 (§19).

`Vec3` 와 `Mat3` 는 `tuple` 파생이다. 그래서

- 불변이고 해시 가능하다. 나중에 carrier 캐시 키로 그대로 쓸 수 있다 (§12-1)
- `np.allclose(v, (0, 0, 1))` 처럼 시퀀스를 받는 자리에 그대로 들어간다
- 인덱싱, 순회, 튜플 비교가 공짜다

hot path 는 이 클래스의 연산자를 쓰지 않고 `v[0]`, `v[1]`, `v[2]` 를 지역
변수로 풀어 float 산술을 직접 한다. 연산자는 읽기 좋아야 하는 저작 계층과
테스트를 위한 것이다.
"""

from __future__ import annotations

import math

from ..epsilon import NORMAL_EPS

__all__ = [
    "Vec3",
    "Mat3",
    "as_vec",
    "clamp",
    "cross",
    "dot",
    "identity3",
    "norm",
    "normalize",
    "orthonormal_basis",
    "rotation_matrix",
]


class Vec3(tuple):
    """길이 3 float 벡터.

    ``Vec3(x, y, z)`` 와 ``Vec3(seq)`` 를 모두 받는다. ``@`` 는 내적이고
    스칼라 곱, 덧셈, 뺄셈, 부호 반전이 있다.

    ``+`` 는 튜플 이어붙이기가 아니라 **벡터 덧셈**이다. 길이 3 벡터를 이어붙일
    일은 없고, 이어붙이기로 두면 조용히 길이 6 튜플이 나와 훨씬 늦게 터진다.
    """

    __slots__ = ()

    def __new__(cls, x, y=None, z=None):
        if y is None:
            x, y, z = x
        return tuple.__new__(cls, (float(x), float(y), float(z)))

    @property
    def x(self) -> float:
        return self[0]

    @property
    def y(self) -> float:
        return self[1]

    @property
    def z(self) -> float:
        return self[2]

    def __matmul__(self, other) -> float:
        return self[0] * other[0] + self[1] * other[1] + self[2] * other[2]

    def __neg__(self) -> "Vec3":
        return tuple.__new__(Vec3, (-self[0], -self[1], -self[2]))

    def __add__(self, other) -> "Vec3":
        return tuple.__new__(
            Vec3, (self[0] + other[0], self[1] + other[1], self[2] + other[2])
        )

    def __sub__(self, other) -> "Vec3":
        return tuple.__new__(
            Vec3, (self[0] - other[0], self[1] - other[1], self[2] - other[2])
        )

    def __mul__(self, k) -> "Vec3":
        k = float(k)
        return tuple.__new__(Vec3, (self[0] * k, self[1] * k, self[2] * k))

    __rmul__ = __mul__

    def __truediv__(self, k) -> "Vec3":
        k = float(k)
        return tuple.__new__(Vec3, (self[0] / k, self[1] / k, self[2] / k))

    def __repr__(self) -> str:
        return f"Vec3({self[0]!r}, {self[1]!r}, {self[2]!r})"


class Mat3(tuple):
    """3x3 행렬. 행 세 개(`Vec3`)를 담는다.

    행 단위로 보관하므로 ``np.asarray(m)`` 이 (3, 3) 이 되고 ``np.linalg.det``
    같은 진단 코드가 그대로 돌아간다. 행렬은 축 집합 생성과 Turn 마다 한 번씩만
    만들어지므로 hot path 가 아니다 (§12).
    """

    __slots__ = ()

    def __new__(cls, rows):
        return tuple.__new__(cls, (Vec3(r) for r in rows))

    def __matmul__(self, other):
        r0, r1, r2 = self
        if isinstance(other, Mat3):
            # (A @ B)[i][j] = sum_k A[i][k] * B[k][j]
            b0, b1, b2 = other
            return Mat3(
                (
                    (
                        r[0] * b0[0] + r[1] * b1[0] + r[2] * b2[0],
                        r[0] * b0[1] + r[1] * b1[1] + r[2] * b2[1],
                        r[0] * b0[2] + r[1] * b1[2] + r[2] * b2[2],
                    )
                    for r in (r0, r1, r2)
                )
            )
        x, y, z = other[0], other[1], other[2]
        return tuple.__new__(
            Vec3,
            (
                r0[0] * x + r0[1] * y + r0[2] * z,
                r1[0] * x + r1[1] * y + r1[2] * z,
                r2[0] * x + r2[1] * y + r2[2] * z,
            ),
        )

    def __neg__(self) -> "Mat3":
        return Mat3((-r for r in self))

    @property
    def T(self) -> "Mat3":
        r0, r1, r2 = self
        return Mat3(
            ((r0[0], r1[0], r2[0]), (r0[1], r1[1], r2[1]), (r0[2], r1[2], r2[2]))
        )

    def __repr__(self) -> str:
        return f"Mat3({tuple(tuple(r) for r in self)!r})"


IDENTITY3 = Mat3(((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))


def identity3() -> Mat3:
    return IDENTITY3


def as_vec(v) -> Vec3:
    """길이 3 `Vec3` 로 변환. 이미 `Vec3` 면 그대로 돌려준다."""
    if type(v) is Vec3:
        return v
    return Vec3(v)


def clamp(x, lo: float = -1.0, hi: float = 1.0) -> float:
    """역삼각함수 정의역 보호 (§14). 스칼라만 받는다.

    예전에는 `np.clip` 이라 배열도 받았지만, 배열이 흘러드는 자리가 없다.
    """
    x = float(x)
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b) -> Vec3:
    return tuple.__new__(
        Vec3,
        (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        ),
    )


def norm(v) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def normalize(v) -> Vec3:
    x, y, z = float(v[0]), float(v[1]), float(v[2])
    length = math.sqrt(x * x + y * y + z * z)
    if length < NORMAL_EPS:
        raise ValueError("영벡터는 정규화할 수 없다")
    return tuple.__new__(Vec3, (x / length, y / length, z / length))


def orthonormal_basis(n) -> tuple[Vec3, Vec3]:
    """법선 n에 수직인 결정적 정규직교기저 (u, v)를 만든다.

    같은 n에 대해 항상 같은 (u, v)가 나와야 한다. 그래야 carrier가 병합될 때
    각도 좌표 변환량이 0에 가깝게 유지된다.

    (u, v, n)은 오른손계다: u x v = n. 따라서 t가 증가하는 방향은
    +n 쪽에서 볼 때 반시계 방향이다.
    """
    x, y, z = float(n[0]), float(n[1]), float(n[2])
    length = math.sqrt(x * x + y * y + z * z)
    if length < NORMAL_EPS:
        raise ValueError("영벡터는 정규화할 수 없다")
    x, y, z = x / length, y / length, z / length

    # n과 가장 덜 평행한 표준 기저축을 고른다. 동률은 낮은 인덱스.
    ax, ay, az = abs(x), abs(y), abs(z)
    if ax <= ay and ax <= az:
        # e = (1, 0, 0);  u = e x n
        ux, uy, uz = 0.0 * z - 0.0 * y, 0.0 * x - 1.0 * z, 1.0 * y - 0.0 * x
    elif ay <= az:
        # e = (0, 1, 0)
        ux, uy, uz = 1.0 * z - 0.0 * y, 0.0 * x - 0.0 * z, 0.0 * y - 1.0 * x
    else:
        # e = (0, 0, 1)
        ux, uy, uz = 0.0 * z - 1.0 * y, 1.0 * x - 0.0 * z, 0.0 * y - 0.0 * x
    un = math.sqrt(ux * ux + uy * uy + uz * uz)
    ux, uy, uz = ux / un, uy / un, uz / un

    # v = n x u
    vx, vy, vz = y * uz - z * uy, z * ux - x * uz, x * uy - y * ux
    return tuple.__new__(Vec3, (ux, uy, uz)), tuple.__new__(Vec3, (vx, vy, vz))


def rotation_matrix(axis, angle: float) -> Mat3:
    """axis를 중심으로 angle(라디안)만큼 도는 회전행렬. Rodrigues 공식.

    +axis 쪽에서 볼 때 반시계 방향이 양의 각이다.

        R = I + sin(angle) K + (1 - cos(angle)) K^2

    K 는 반대칭 행렬이고 단위축에서 ``K^2 = a a^T - I`` 다. 항등식으로 줄이지
    않고 곱을 그대로 쓴다. 줄이면 대각 성분의 반올림 경로가 달라진다 (§14).
    """
    ax, ay, az = normalize(axis)
    k = Mat3(((0.0, -az, ay), (az, 0.0, -ax), (-ay, ax, 0.0)))
    kk = k @ k
    s = math.sin(angle)
    c = 1.0 - math.cos(angle)
    ident = IDENTITY3
    return Mat3(
        (
            (
                ident[i][j] + s * k[i][j] + c * kk[i][j]
                for j in range(3)
            )
            for i in range(3)
        )
    )
