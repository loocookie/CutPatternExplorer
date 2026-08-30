// 브라우저에 올라가는 JS 가 실제로 파싱되는가.
//
//   node web/syntax.test.js
//
// 이걸 안 봐서 오래 헤맸다. worker.js 안에 파이썬을 백틱 템플릿 리터럴로
// 박아 뒀는데, 파이썬 docstring 이 백틱을 쓰는 순간 리터럴이 거기서 끊겨
// 파일 전체가 문법 오류가 됐다. 브라우저는 **빈 메시지의 로드 실패**만
// 알려 주므로 원인이 안 보인다.
//
// 파이썬 테스트는 전부 통과하고 있었다. 문자열을 오려내는 방식이라 JS 문법과
// 무관했기 때문이다.

"use strict";
const fs = require("fs");
const path = require("path");

let failures = 0;
function check(name, cond, extra) {
  if (cond) console.log("  OK   " + name);
  else { failures++; console.log("  FAIL " + name, extra !== undefined ? extra : ""); }
}

const FILES = ["render.js", "editor.js", "share.js", "app.js", "worker.js", "vocab.js"];

for (const name of FILES) {
  const full = path.join(__dirname, name);
  if (!fs.existsSync(full)) { check(name + " 존재", false); continue; }
  const text = fs.readFileSync(full, "utf8");
  let ok = true, err = "";
  try {
    // import 는 함수 본문에서 못 쓰므로 동적 import 만 있는지도 함께 걸린다
    new Function(text.replace(/^window\./gm, "globalThis."));
  } catch (e) { ok = false; err = e.message; }
  check(name + " 파싱", ok, err);
}

// index.html 안의 인라인 스크립트도 마찬가지다
{
  const html = fs.readFileSync(path.join(__dirname, "index.html"), "utf8");
  const i = html.lastIndexOf("<script>"), j = html.lastIndexOf("</script>");
  let ok = true, err = "";
  try { new Function(html.slice(i + 8, j)); } catch (e) { ok = false; err = e.message; }
  check("index.html 인라인 스크립트 파싱", ok, err);
}

// 백틱 템플릿 리터럴 안에 다른 언어를 박지 않는다
{
  const worker = fs.readFileSync(path.join(__dirname, "worker.js"), "utf8");
  check("worker.js 에 파이썬을 박아 두지 않는다",
    !worker.includes("const BOOT = `"),
    "web/boot.py 로 빼 두었다");
}

console.log(failures === 0 ? "\n전부 통과" : "\n실패 " + failures + "개");
process.exit(failures === 0 ? 0 : 1);
