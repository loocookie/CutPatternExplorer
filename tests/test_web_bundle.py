"""브라우저용 엔진 번들. 설계 문서 §19.

`web/engine.js` 는 생성물이지만 커밋한다 — GitHub Pages 가 저장소를 그대로
서빙하므로 (§19.2) 없으면 배포가 조용히 깨진다.

커밋한다는 것은 **어긋날 수 있다**는 뜻이다. 소스를 고치고 번들을 다시 만들지
않으면 브라우저에서만 옛 코드가 돈다. 로컬 테스트는 전부 통과하므로 알아챌
방법이 없다. 그래서 여기서 막는다.
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

import bundle_engine  # noqa: E402

BUNDLE = ROOT / "web" / "engine.js"


def _bundled() -> dict[str, str]:
    text = BUNDLE.read_text(encoding="utf-8")
    start = text.index("{")
    end = text.rindex("}") + 1
    return json.loads(text[start:end])


def test_bundle_exists():
    assert BUNDLE.exists(), "python web/bundle_engine.py 를 돌린다"


def test_bundle_matches_the_sources():
    """번들이 현재 소스와 한 글자도 다르지 않은가."""
    current = bundle_engine.collect()
    bundled = _bundled()

    missing = sorted(set(current) - set(bundled))
    extra = sorted(set(bundled) - set(current))
    assert not missing, f"번들에 빠진 파일: {missing}. python web/bundle_engine.py"
    assert not extra, f"번들에만 있는 파일: {extra}. python web/bundle_engine.py"

    stale = sorted(k for k in current if current[k] != bundled[k])
    assert not stale, f"번들이 낡았다: {stale}. python web/bundle_engine.py"


def test_bundle_leaves_out_the_vpython_viewer():
    """브라우저에서 외부 의존을 끌고 오면 안 된다 (§11.2)."""
    bundled = _bundled()
    assert "cutpattern/render/vpython_view.py" not in bundled

    # 문자열 훑기로는 docstring 안의 예시 코드까지 import 로 센다. AST 로 본다
    allowed = {
        "__future__", "math", "json", "itertools", "dataclasses",
        "functools", "collections", "contextlib", "typing",
        # boot.py 가 좌표를 바이트열로 넘길 때 쓴다 (§11.1)
        "array", "sys", "cutpattern",
    }
    for path, source in bundled.items():
        for node in ast.walk(ast.parse(source, filename=path)):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue  # 패키지 안의 상대 import
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            for name in names:
                assert name in allowed, f"{path}: 외부 의존 {name!r}"


def test_every_engine_module_is_bundled():
    """`__init__.py` 를 빠뜨리면 패키지가 import 되지 않는다."""
    bundled = _bundled()
    for name in ("cutpattern/__init__.py", "cutpattern/geometry/__init__.py",
                 "cutpattern/engine/__init__.py", "cutpattern/render/__init__.py"):
        assert name in bundled
    assert "cutpattern/render/scene.py" in bundled
