// 정의를 링크에 싣는다. 설계 문서 §19.4.
//
// 코드는 URL **fragment**(`#`)에 넣는다. fragment 는 서버로 전송되지 않으므로
// 호스팅 쪽에 남의 정의가 로그로 남지 않는다 (§19.3).
//
// **받은 코드를 자동으로 실행하지 않는다.** 링크를 여는 것이 곧 임의 코드
// 실행이 되면 안 된다. 불러온 코드는 편집창에 채워만 넣고, 사람이 읽고
// 실행을 누른다. 브라우저 샌드박스는 파일 접근과 다른 출처 요청은 막지만
// 무한 루프로 탭을 멈추는 것이나 fetch 로 데이터를 보내는 것은 막지 못한다.

"use strict";

const KEY = "code=";
// 각도는 code= 뒤에 별도 조각으로 붙는다 (#code=...&angles=...). code= 의
// 압축·복원 계약은 그대로 두고, 각도는 작은 JSON 이라 압축 없이 base64url
// 만 한다. 두 키 다 base64url 이라 "=" 나 "&" 를 안 써서 & 로 안전하게 갈린다
const ANGLES_KEY = "angles=";

// 브라우저 주소창이 감당하는 실용 한도. 넘으면 잘릴 수 있어 미리 알린다
const SAFE_URL_LENGTH = 8000;

function bytesToBase64url(bytes) {
  // btoa 는 latin1 만 받는다. 큰 배열을 한 번에 넘기면 인자 개수 제한에
  // 걸리므로 나눠서 문자열로 만든다
  let binary = "";
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function base64urlToBytes(text) {
  const padded = text.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(padded + "=".repeat((4 - (padded.length % 4)) % 4));
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

async function through(stream, bytes) {
  const blob = new Blob([bytes]);
  const piped = blob.stream().pipeThrough(stream);
  return new Uint8Array(await new Response(piped).arrayBuffer());
}

// 압축이 없는 환경에서도 링크는 되어야 한다. 앞 글자로 어느 쪽인지 구분한다
const RAW = "r";
const DEFLATE = "d";

async function encodeSource(text) {
  const bytes = new TextEncoder().encode(text);
  if (typeof CompressionStream === "function") {
    try {
      const packed = await through(new CompressionStream("deflate-raw"), bytes);
      // 짧은 정의는 압축이 오히려 커진다. 작은 쪽을 쓴다
      if (packed.length < bytes.length) return DEFLATE + bytesToBase64url(packed);
    } catch (_) { /* 아래 raw 로 떨어진다 */ }
  }
  return RAW + bytesToBase64url(bytes);
}

async function decodeSource(payload) {
  const kind = payload[0];
  const bytes = base64urlToBytes(payload.slice(1));
  if (kind === DEFLATE) {
    const raw = await through(new DecompressionStream("deflate-raw"), bytes);
    return new TextDecoder().decode(raw);
  }
  if (kind === RAW) return new TextDecoder().decode(bytes);
  throw new Error("Unknown link format");
}

function encodeAngles(angles) {
  return bytesToBase64url(new TextEncoder().encode(JSON.stringify(angles)));
}

function decodeAngles(payload) {
  return JSON.parse(new TextDecoder().decode(base64urlToBytes(payload)));
}

/** 현재 주소를 바탕으로 공유 링크를 만든다. `angles` 는 선택이다 — 없거나
 * 비어 있으면 그 조각을 아예 안 붙인다. 옛 링크와 모양이 같아진다. */
async function shareLink(text, baseUrl, angles) {
  const base = (baseUrl || "").split("#")[0];
  let hash = "#" + KEY + (await encodeSource(text));
  if (angles && Object.keys(angles).length) {
    hash += "&" + ANGLES_KEY + encodeAngles(angles);
  }
  return base + hash;
}

/** fragment 에서 정의를 꺼낸다. 없으면 null.
 *
 * `&` 로 조각을 가른다 — angles= 가 뒤에 붙어도 code= 조각만 정확히 뗀다.
 */
async function sourceFromHash(hash) {
  const raw = (hash || "").replace(/^#/, "");
  const part = raw.split("&").find((p) => p.startsWith(KEY));
  if (part === undefined) return null;
  return decodeSource(part.slice(KEY.length));
}

/** fragment 에서 각도를 꺼낸다. 없거나 손상됐으면 null — 코드를 읽는 것을
 * 막을 이유가 없으므로 여기서는 예외를 던지지 않는다. */
function anglesFromHash(hash) {
  const raw = (hash || "").replace(/^#/, "");
  const part = raw.split("&").find((p) => p.startsWith(ANGLES_KEY));
  if (part === undefined) return null;
  try { return decodeAngles(part.slice(ANGLES_KEY.length)); }
  catch (_) { return null; }
}

const Share = {
  encodeSource, decodeSource, shareLink, sourceFromHash, anglesFromHash,
  SAFE_URL_LENGTH, KEY,
};
if (typeof window !== "undefined") window.Share = Share;
if (typeof module !== "undefined") module.exports = Share;
