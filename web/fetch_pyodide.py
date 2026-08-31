"""Pyodide 런타임을 받아 `web/pyodide/` 에 둔다. 설계 문서 §19.14.

    python web/fetch_pyodide.py

정의가 `fetch` 를 쓸 수 있는 구멍을 CSP `connect-src` 로 잠그려면 런타임이
같은 출처에서 와야 한다. CDN 에서 받는 한 그 출처를 열어 두어야 하기 때문이다.

**파일은 커밋하지 않는다.** 12MB 가 판올림마다 히스토리에 영구히 쌓인다.
커밋의 값은 크기가 아니라 "로컬과 배포가 같다는 것을 무엇이 보증하는가" 인데,
그 보증은 `web/pyodide.sha256` 300바이트로 살 수 있다. 오히려 더 강하다 —
커밋은 최초 1회를 눈감고 받지만 이것은 **매번** 검증한다. CDN 이 오염되면
빌드가 죽는다.

**CDN 폴백을 넣지 않는다.** 폴백이 있으면 잠그려던 구멍이 그대로 남고, 로컬에만
파일이 없는 상태를 아무도 못 알아챈다. 스크립트를 안 돌리면 `pyodide.mjs` 가
404 로 **시끄럽게** 죽는 편이 낫다.

버전이 적히는 곳은 `pyodide.sha256` 하나다. worker.js 에는 버전이 없다.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "web" / "pyodide.sha256"
TARGET = ROOT / "web" / "pyodide"

CDN = "https://cdn.jsdelivr.net/pyodide/v%s/full/%s"


def manifest() -> tuple[str, dict[str, str]]:
    """`pyodide.sha256` 을 읽는다. `version` 한 줄과 `<해시>  <이름>` 들."""
    version = ""
    files: dict[str, str] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("version "):
            version = line.split(None, 1)[1].strip()
            continue
        digest, name = line.split()
        files[name] = digest
    if not version or not files:
        raise SystemExit(f"{MANIFEST.name} 에 version 이나 파일 목록이 없다")
    return version, files


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    version, files = manifest()
    TARGET.mkdir(parents=True, exist_ok=True)

    wrong: list[str] = []
    for name, expected in files.items():
        path = TARGET / name
        if path.exists() and sha256(path) == expected:
            print(f"  있음  {name}")
            continue
        url = CDN % (version, name)
        print(f"  받음  {name}  <- {url}")
        # 받다가 죽으면 반쯤 쓴 파일이 남는다. 다음 실행이 해시로 잡아 다시 받는다
        with urllib.request.urlopen(url) as response:
            path.write_bytes(response.read())
        actual = sha256(path)
        if actual != expected:
            # 못 믿을 것을 남겨 두지 않는다. 다음 실행이 이걸 "있음" 으로 볼 수도 없다
            path.unlink()
            wrong.append(f"    {actual}  {name}")

    if wrong:
        print(f"\n해시가 안 맞는다 (v{version}). 받은 것은 지웠다.\n")
        print("\n".join(wrong))
        print(
            f"\n판올림 중이면 위 값을 {MANIFEST.name} 에 옮겨 적고 다시 돌려라."
            "\n버전을 안 바꿨는데 이게 나오면 CDN 이 준 것이 전과 다르다는 뜻이다."
        )
        sys.exit(1)

    # 목록에 없는 것은 지운다. 판올림 때 옛 파일이 남으면 브라우저가 그걸
    # 계속 쓸 수 있고, 그 어긋남은 브라우저에서만 보인다 (§19.11)
    for path in TARGET.iterdir():
        if path.name not in files:
            print(f"  지움  {path.name}  (목록에 없다)")
            path.unlink()

    total = sum((TARGET / name).stat().st_size for name in files)
    print(f"\n  Pyodide {version}  파일 {len(files)}개  {total / 1024 / 1024:.0f}MB"
          f"  -> web/{TARGET.name}/")


if __name__ == "__main__":
    main()
