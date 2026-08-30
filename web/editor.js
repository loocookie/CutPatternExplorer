// 편집창의 들여쓰기. 설계 문서 §19.6.
//
// textarea 는 Tab 이 포커스 이동이다. 파이썬은 들여쓰기가 문법이므로 그대로는
// 정의를 쓸 수 없다.
//
// 들여쓰기는 **스페이스 4칸**이다. 파이썬 관례이고 이 저장소의 정의들이 쓰는
// 폭이다. 다만 늘 4칸을 넣지 않고 다음 배수 자리까지 넣는다 — 열이 어긋나면
// 파이썬에서는 문법 오류다.
//
// 함수들은 **바꿀 구간만** 돌려준다 (`{from, to, insert, start, end}`).
// 전체 텍스트를 갈아치우면 되돌리기가 뭉텅이가 되고, 커서 계산도 DOM 에 묶여
// 브라우저 없이는 확인할 수 없다.

"use strict";

const WIDTH = 4;

function lineStartAt(text, pos) {
  return text.lastIndexOf("\n", pos - 1) + 1;
}

function lineEndAt(text, pos) {
  const i = text.indexOf("\n", pos);
  return i === -1 ? text.length : i;
}

/** 선택이 걸친 줄 전체의 범위. 끝이 줄머리면 그 줄은 빼고 본다. */
function blockRange(text, start, end) {
  const from = lineStartAt(text, start);
  let last = end;
  if (end > start && text[end - 1] === "\n") last = end - 1;
  return [from, lineEndAt(text, last)];
}

function spansLines(text, start, end) {
  return text.slice(start, end).includes("\n");
}

/** Tab. 여러 줄이 걸리면 줄마다 넣고, 아니면 다음 정렬 자리까지 넣는다. */
function indent({ text, start, end }) {
  if (start !== end && spansLines(text, start, end)) {
    const [from, to] = blockRange(text, start, end);
    const insert = text.slice(from, to).split("\n")
      .map((l) => " ".repeat(WIDTH) + l).join("\n");
    return { from, to, insert, start: from, end: from + insert.length };
  }
  const column = start - lineStartAt(text, start);
  const insert = " ".repeat(WIDTH - (column % WIDTH));
  const at = start + insert.length;
  return { from: start, to: end, insert, start: at, end: at };
}

/** Shift+Tab. 줄머리 공백을 최대 WIDTH 만큼 덜어낸다. */
function dedent({ text, start, end }) {
  const [from, to] = blockRange(text, start, end);
  let firstCut = 0;
  const insert = text.slice(from, to).split("\n").map((line, i) => {
    let cut = 0;
    while (cut < WIDTH && line[cut] === " ") cut++;
    if (cut === 0 && line[0] === "\t") cut = 1;
    if (i === 0) firstCut = cut;
    return line.slice(cut);
  }).join("\n");

  if (start !== end && spansLines(text, start, end)) {
    return { from, to, insert, start: from, end: from + insert.length };
  }
  const at = Math.max(from, start - firstCut);
  return { from, to, insert, start: at, end: at };
}

/** Enter. 앞 줄의 들여쓰기를 잇고, 콜론으로 끝나면 한 단 더 들어간다. */
function newline({ text, start, end }) {
  const from = lineStartAt(text, start);
  const before = text.slice(from, start);
  const lead = (before.match(/^[ \t]*/) || [""])[0];
  // 주석 안의 콜론은 문법이 아니다
  const code = before.split("#")[0].trimEnd();
  const insert = "\n" + lead + (code.endsWith(":") ? " ".repeat(WIDTH) : "");
  const at = start + insert.length;
  return { from: start, to: end, insert, start: at, end: at };
}

/** 우리가 다루는 키면 편집을, 아니면 null 을 돌려준다. */
function handleKey(state, key, shift) {
  if (key === "Tab") return shift ? dedent(state) : indent(state);
  if (key === "Enter") return newline(state);
  return null;
}

/** 편집을 적용한 결과. 테스트와 진단용이다. */
function apply(text, edit) {
  return text.slice(0, edit.from) + edit.insert + text.slice(edit.to);
}

/**
 * textarea 에 붙인다.
 *
 * Tab 을 가로채면 키보드로 빠져나갈 길이 막힌다. Escape 를 누르면 그 다음
 * Tab 은 원래대로 포커스를 옮긴다 — 흔히 쓰는 탈출구다.
 */
function attach(textarea) {
  let escaped = false;
  textarea.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") { escaped = true; return; }
    if (ev.key === "Tab" && escaped) { escaped = false; return; }  // 포커스 이동
    escaped = false;
    if (ev.ctrlKey || ev.metaKey || ev.altKey) return;

    const edit = handleKey(
      { text: textarea.value, start: textarea.selectionStart, end: textarea.selectionEnd },
      ev.key, ev.shiftKey
    );
    if (!edit) return;
    ev.preventDefault();
    // 바뀐 구간만 갈아 끼운다. setRangeText 는 되돌리기 기록에 남는다
    textarea.setRangeText(edit.insert, edit.from, edit.to, "end");
    textarea.selectionStart = edit.start;
    textarea.selectionEnd = edit.end;
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

const Editor = { WIDTH, indent, dedent, newline, handleKey, apply, attach };
if (typeof window !== "undefined") window.Editor = Editor;
if (typeof module !== "undefined") module.exports = Editor;
