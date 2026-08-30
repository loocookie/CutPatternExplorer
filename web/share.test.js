// 링크 왕복. 설계 문서 §19.4.
//
//   node web/share.test.js

"use strict";
const Share = require("./share.js");

let failures = 0;
function check(name, cond, extra) {
  if (cond) console.log("  OK   " + name);
  else { failures++; console.log("  FAIL " + name, extra !== undefined ? extra : ""); }
}

(async () => {
  const source = `from cutpattern import solids as S
from cutpattern.dsl import at_angle, puzzle, split, turned

# 한글 주석도 왕복해야 한다. 정의는 대부분 주석이 붙는다
faces = S.cube("faces", turns=(45, -45, 90, -90, 180))

with puzzle("OctoCube Master", faces) as p:
    split(faces)
    for x in faces:
        with turned(x, 45):
            split(*at_angle(x, 90, faces))
`;

  const payload = await Share.encodeSource(source);
  check("압축된 형식을 고른다", payload[0] === "d", payload[0]);
  check("URL 에 안전한 글자만 쓴다", /^[A-Za-z0-9\-_]+$/.test(payload.slice(1)));
  check("왕복하면 한 글자도 다르지 않다", (await Share.decodeSource(payload)) === source);

  const link = await Share.shareLink(source, "https://example.github.io/cut/#code=옛것");
  check("fragment 에만 싣는다", link.split("#")[0] === "https://example.github.io/cut/");
  check("링크가 실용 한도 안이다", link.length < Share.SAFE_URL_LENGTH, link.length);
  check("링크에서 그대로 꺼낸다",
    (await Share.sourceFromHash("#" + link.split("#")[1])) === source);

  check("fragment 가 없으면 null", (await Share.sourceFromHash("")) === null);
  check("다른 fragment 는 무시한다", (await Share.sourceFromHash("#anchor")) === null);

  // 압축이 커지는 짧은 입력은 raw 로 간다
  const tiny = "p=1";
  const rawPayload = await Share.encodeSource(tiny);
  check("짧으면 raw 를 고른다", rawPayload[0] === "r", rawPayload);
  check("raw 도 왕복한다", (await Share.decodeSource(rawPayload)) === tiny);

  // 압축 API 가 없는 환경
  const saved = global.CompressionStream;
  global.CompressionStream = undefined;
  const noCompress = await Share.encodeSource(source);
  global.CompressionStream = saved;
  check("압축이 없어도 링크가 된다", noCompress[0] === "r");
  check("그 링크도 왕복한다", (await Share.decodeSource(noCompress)) === source);

  let threw = false;
  try { await Share.decodeSource("x???"); } catch (_) { threw = true; }
  check("모르는 형식은 거부한다", threw);

  console.log(failures === 0 ? "\n전부 통과" : "\n실패 " + failures + "개");
  process.exit(failures === 0 ? 0 : 1);
})();
