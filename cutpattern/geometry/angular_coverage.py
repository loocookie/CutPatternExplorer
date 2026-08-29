"""원형 각도 구간 집합 연산. 설계 문서 §3, §5, §6.1.

coverage 표현 규약
------------------
- span 은 ``(t0, t1)`` 이고 ``0 <= t0 < t1 <= TAU``.
- ``0 / TAU`` 를 가로지르는 구간은 두 개로 분해해 저장한다 (§5).
- 리스트는 t0 기준 정렬, 서로 겹치지 않음.

Split 이 다른 원과의 교점을 전혀 계산하지 않아도 되는 이유가 여기 있다.
같은 carrier 원 위의 구간끼리만 union / difference 하면 된다 (§3).
"""

from __future__ import annotations

import math

from ..epsilon import ANGLE_EPS

TAU = 2.0 * math.pi

Span = tuple[float, float]
Coverage = list[Span]

__all__ = [
    "TAU",
    "empty",
    "full",
    "wrap_angle",
    "make_span",
    "normalize_spans",
    "union",
    "difference",
    "intersection",
    "is_full",
    "is_empty",
    "total_length",
    "contains",
    "shift",
    "reflect",
]


def empty() -> Coverage:
    return []


def full() -> Coverage:
    return [(0.0, TAU)]


def wrap_angle(t: float) -> float:
    """[0, TAU) 로 접는다."""
    t = math.fmod(t, TAU)
    if t < 0.0:
        t += TAU
    # fmod 결과가 -1e-17 같은 값이면 위에서 TAU 가 되어버린다
    if t >= TAU:
        t = 0.0
    return t


def make_span(t0: float, length: float) -> Coverage:
    """시작각과 길이로 span 을 만든다. 필요하면 seam 에서 분해한다.

    길이를 그대로 보존하므로 shift / reflect 에서 오차가 누적되지 않는다.
    """
    if length <= ANGLE_EPS:
        return []
    if length >= TAU - ANGLE_EPS:
        return full()
    s = wrap_angle(t0)
    e = s + length
    if e <= TAU:
        return [(s, e)]
    return [(s, TAU), (0.0, e - TAU)]


def normalize_spans(spans: Coverage) -> Coverage:
    """정렬 + 인접/중첩 병합 + 미세 구간 제거."""
    items = [(float(a), float(b)) for a, b in spans if b - a > ANGLE_EPS]
    if not items:
        return []
    items.sort()
    out: Coverage = [items[0]]
    for s, e in items[1:]:
        ls, le = out[-1]
        if s <= le + ANGLE_EPS:
            if e > le:
                out[-1] = (ls, e)
        else:
            out.append((s, e))
    # 부동소수로 TAU 를 살짝 넘긴 끝점 정리
    ls, le = out[-1]
    if le > TAU:
        out[-1] = (ls, TAU)
    return out


def union(a: Coverage, b: Coverage) -> Coverage:
    return normalize_spans(list(a) + list(b))


def difference(a: Coverage, b: Coverage) -> Coverage:
    """a 에서 b 를 뺀 나머지. Split 의 ``ΔE = C - E`` 가 이것이다 (§3, §6.1)."""
    a = normalize_spans(a)
    b = normalize_spans(b)
    if not b:
        return a
    out: Coverage = []
    for cs, ce in a:
        cur = [(cs, ce)]
        for bs, be in b:
            nxt: Coverage = []
            for s, e in cur:
                if be <= s + ANGLE_EPS or bs >= e - ANGLE_EPS:
                    nxt.append((s, e))
                    continue
                if bs > s + ANGLE_EPS:
                    nxt.append((s, min(bs, e)))
                if be < e - ANGLE_EPS:
                    nxt.append((max(be, s), e))
            cur = nxt
            if not cur:
                break
        out.extend(cur)
    return normalize_spans(out)


def intersection(a: Coverage, b: Coverage) -> Coverage:
    a = normalize_spans(a)
    b = normalize_spans(b)
    out: Coverage = []
    i = j = 0
    while i < len(a) and j < len(b):
        s = max(a[i][0], b[j][0])
        e = min(a[i][1], b[j][1])
        if e - s > ANGLE_EPS:
            out.append((s, e))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return normalize_spans(out)


def is_empty(spans: Coverage) -> bool:
    return not normalize_spans(spans)


def is_full(spans: Coverage) -> bool:
    """[0, TAU) 를 빠짐없이 덮는가.

    §7.1 의 Turn 합법성 판정이 이 함수 하나로 끝난다.
    """
    n = normalize_spans(spans)
    if len(n) != 1:
        return False
    return n[0][0] <= ANGLE_EPS and n[0][1] >= TAU - ANGLE_EPS


def total_length(spans: Coverage) -> float:
    return sum(e - s for s, e in normalize_spans(spans))


def contains(spans: Coverage, t: float) -> bool:
    t = wrap_angle(t)
    for s, e in normalize_spans(spans):
        if s - ANGLE_EPS <= t <= e + ANGLE_EPS:
            return True
    return False


def shift(spans: Coverage, delta: float) -> Coverage:
    """모든 구간을 delta 만큼 회전. t -> t + delta."""
    out: Coverage = []
    for s, e in normalize_spans(spans):
        out.extend(make_span(s + delta, e - s))
    return normalize_spans(out)


def reflect(spans: Coverage, c: float) -> Coverage:
    """t -> c - t. carrier 가 반대 법선으로 병합될 때 쓴다 (§4.3)."""
    out: Coverage = []
    for s, e in normalize_spans(spans):
        out.extend(make_span(c - e, e - s))
    return normalize_spans(out)
