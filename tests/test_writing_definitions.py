"""docs/writing-definitions.md 가 어휘와 어긋나지 않는지 본다.

이름이 늘거나 사라져도 산문은 조용히 낡을 수 있다. 여기서는 낡음 자체를
막지는 못해도, **이름이 아예 빠지는 것**은 시끄럽게 잡는다 — dsl.__all__
에 새 이름이 생겼는데 문서에 안 적히는 경우다.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = (ROOT / "docs" / "writing-definitions.md").read_text(encoding="utf-8")


def test_every_dsl_name_is_mentioned():
    import cutpattern.dsl as dsl

    missing = [name for name in dsl.__all__ if name not in DOC]
    assert not missing, f"docs/writing-definitions.md 에 없는 이름: {missing}"


def test_every_solids_family_is_mentioned():
    """프리셋 개별 이름은 문서에 안 박는다 — §19.7 이 이미 겪은 문제다.

    개수를 하드코딩하면 프리셋을 늘릴 때마다 문서가 조용히 낡는다. 그래서
    문서는 계열 이름만 적고, 정확한 목록은 편집기의 Add axis set 메뉴를
    가리킨다. 여기서는 그 계열들이 언급은 되어 있는지만 본다.
    """
    for word in ("Platonic", "Catalan", "prism", "antiprism",
                 "bipyramid", "trapezohedron"):
        assert word in DOC, word


def test_the_readme_points_to_it():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/writing-definitions.md" in readme


def test_the_worked_examples_actually_run():
    """문서에 적힌 예제가 실제로 도는가.

    산문은 검사할 수 없어도 코드는 할 수 있다. 여기서 죽으면 그 예제부터
    다시 손으로 확인한다.
    """
    import re

    import pytest

    from cutpattern import solids as S  # noqa: F401
    from cutpattern.dsl import at_angle, carry, nearest, puzzle, split, turned  # noqa: F401

    blocks = re.findall(r"```python\n(.*?)\n```", DOC, re.DOTALL)
    ran = 0
    for block in blocks:
        if "with puzzle(" not in block:
            continue   # 완결된 정의가 아니라 문법 조각(§7 의 rotate 예시 등)
        ns = {
            "cube": S.cube, "octahedron": S.octahedron,
            "tetrahedron": S.tetrahedron,
            "rhombic_dodecahedron": S.rhombic_dodecahedron,
            "puzzle": puzzle, "split": split, "turn": turned,
            "turned": turned, "carry": carry,
            "at_angle": at_angle, "nearest": nearest,
        }
        exec(compile(block, "<doc example>", "exec"), ns)
        ran += 1
    assert ran >= 3, "완결된 정의 예제를 못 찾았다 — 정규식이 문서 형식과 어긋난 것 같다"
