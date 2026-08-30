// 편집창 들여쓰기. 설계 문서 §19.6.
//
//   node web/editor.test.js
//
// 커서와 선택 범위 계산이 틀리기 쉬운데, 손으로 확인하면 "대충 맞는 것 같다"
// 에서 멈춘다. 경계만 골라 본다.

"use strict";
const E = require("./editor.js");

let failures = 0;
function check(name, cond, extra) {
  if (cond) console.log("  OK   " + name);
  else { failures++; console.log("  FAIL " + name, extra !== undefined ? JSON.stringify(extra) : ""); }
}

const st = (text, start, end) => ({ text, start, end: end === undefined ? start : end });

function run(text, start, end, key, shift) {
  const edit = E.handleKey(st(text, start, end), key, shift);
  return { text: E.apply(text, edit), start: edit.start, end: edit.end };
}

// ---- Tab 은 다음 배수 자리까지 -----------------------------------------

check("빈 줄에서 4칸", run("", 0, 0, "Tab").text === "    ");
check("열 3 에서는 1칸만 (열을 4에 맞춘다)", run("abc", 3, 3, "Tab").text === "abc ");
check("열 4 에서는 다시 4칸", run("    x", 4, 4, "Tab").text === "        x");
check("커서가 넣은 만큼 간다", run("abc", 3, 3, "Tab").start === 4);

// 선택이 한 줄 안이면 그 선택을 지우고 넣는다 (평범한 타이핑과 같다)
check("한 줄 선택은 대체된다", run("abXYc", 2, 4, "Tab").text === "ab  c",
  run("abXYc", 2, 4, "Tab"));

// ---- 여러 줄 -----------------------------------------------------------

const block = "a\nb\nc";
{
  const out = run(block, 0, 5, "Tab");
  check("여러 줄이면 줄마다 넣는다", out.text === "    a\n    b\n    c", out);
  check("선택이 블록 전체를 덮는다", out.start === 0 && out.end === out.text.length, out);
}
{
  // 선택 끝이 줄머리면 그 줄은 건드리지 않는다. 아래 줄까지 밀리면 놀란다
  const out = run("a\nb\nc", 0, 2, "Tab");
  check("끝이 줄머리면 그 줄은 제외", out.text === "    a\nb\nc", out);
}

// ---- Shift+Tab ---------------------------------------------------------

check("줄머리 4칸을 덜어낸다", run("    abc", 7, 7, "Tab", true).text === "abc");
check("4칸보다 적으면 있는 만큼만", run("  abc", 5, 5, "Tab", true).text === "abc");
check("공백이 없으면 그대로", run("abc", 3, 3, "Tab", true).text === "abc");
check("탭 문자도 한 칸으로 친다", run("\tabc", 4, 4, "Tab", true).text === "abc");
{
  const out = run("    a\n    b", 0, 11, "Tab", true);
  check("여러 줄을 함께 덜어낸다", out.text === "a\nb", out);
}
{
  // 커서가 들여쓰기 안쪽이면 줄머리보다 앞으로 가면 안 된다
  const out = run("    abc", 2, 2, "Tab", true);
  check("커서가 줄머리 앞으로 안 간다", out.start >= 0 && out.start <= out.text.length, out);
}

// ---- Enter 자동 들여쓰기 -----------------------------------------------

check("콜론 뒤에는 한 단 더", run("if x:", 5, 5, "Enter").text === "if x:\n    ");
check("들여쓰기를 잇는다", run("    y = 1", 9, 9, "Enter").text === "    y = 1\n    ");
check("평범한 줄은 그대로", run("y = 1", 5, 5, "Enter").text === "y = 1\n");
check("주석 안의 콜론은 문법이 아니다",
  run("x = 1  # 왜: 그래서", 18, 18, "Enter").text.endsWith("\n"),
  run("x = 1  # 왜: 그래서", 18, 18, "Enter"));
check("들여쓴 콜론은 두 단이 된다",
  run("    for x in y:", 15, 15, "Enter").text === "    for x in y:\n        ");

// 줄 가운데에서 Enter — 뒤쪽이 다음 줄로 간다
{
  const out = run("if x: pass", 5, 5, "Enter");
  check("줄 가운데 Enter 도 뒤를 살린다", out.text === "if x:\n     pass", out);
}

// ---- 다루지 않는 키 ----------------------------------------------------

check("다른 키는 건드리지 않는다", E.handleKey(st("a", 1), "a", false) === null);

// ---- 실제 정의로 왕복 --------------------------------------------------
//
// 기본 정의를 통째로 한 단 넣었다가 빼면 원래대로 와야 한다

const source = require("fs").readFileSync(__dirname + "/index.html", "utf8");
const i = source.indexOf("const DEFAULT_SOURCE = `") + "const DEFAULT_SOURCE = `".length;
const def = source.slice(i, source.indexOf("`;", i));
{
  const inOut = run(def, 0, def.length, "Tab");
  const back = run(inOut.text, inOut.start, inOut.end, "Tab", true);
  check("기본 정의를 넣었다 빼면 원래대로", back.text === def);
  // 끝의 개행 뒤 빈 줄은 들여쓰지 않는다. 그러면 파일 끝에 공백만 남는다
  const real = def.replace(/\n$/, "").split("\n").length;
  check("내용이 있는 줄만 들여쓴다", inOut.text.length === def.length + 4 * real,
    { got: inOut.text.length - def.length, expected: 4 * real });
}

console.log(failures === 0 ? "\n전부 통과" : "\n실패 " + failures + "개");
process.exit(failures === 0 ? 0 : 1);
