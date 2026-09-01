// worker 와 주고받는 쪽. 설계 문서 §19.5.
//
// 정의는 worker 안에서만 돈다 (web/worker.js). 여기서는 요청을 보내고 결과
// 데이터를 받을 뿐이라, 남이 쓴 코드가 이 스레드의 DOM 에 닿지 않는다.
//
// 덤으로 평가가 UI 를 멈추지 않는다. 메인 스레드에서 돌 때는 슬라이더를 미는
// 동안 평가 시간만큼 드래그가 끊겼다.

"use strict";

// 부팅이 조용히 멎으면 "Starting…" 이 영원히 남는다. 원인이 화면에 아무것도
// 남기지 않는 종류라 — CSP 차단, worker 스크립트 로드 실패 — 기다리는 것과
// 죽은 것을 구별할 수 없다.
//
// **죽이지는 않는다.** 런타임을 자체 호스팅하므로 (§19.13) 느린 연결에서는
// 이 시간이 정상적으로 넘어갈 수 있다. 아직 오는 중인 것을 끊으면 진짜 고장을
// 하나 만들어 내는 셈이다. 말만 하고 계속 기다린다.
const BOOT_SILENCE_MS = 20000;

// worker 를 **blob 으로 띄운다** (§19.14).
//
// worker 는 문서의 CSP 를 물려받지 않는다 — worker 전역의 정책은 worker
// 스크립트의 **응답 헤더**에서 오는데, GitHub Pages 는 헤더를 줄 수 없다.
// 예외가 하나 있다: 스크립트의 출처가 `blob:` 같은 로컬 스킴이면 만든 쪽의
// 정책을 물려받는다. 그래야 `connect-src` 가 정의가 도는 곳에 실제로 닿는다.
//
// **본문을 blob 에 넣지 않는다.** 넣으면 worker.js 안의 상대 경로가 다 깨진다 —
// blob URL 에는 디렉터리가 없다. import 한 줄만 넣으면 worker.js 는 여전히
// 제 https 주소에서 받아지고, 모듈의 상대 지정자는 **그 모듈의 base URL** 로
// 풀린다. `./engine.js` 도 `./pyodide/` 도 그대로다.
//
// CSP 는 스크립트가 아니라 **전역**에 붙으므로, https 에서 온 worker.js 가
// 그 안에서 돌아도 물려받은 정책 아래 있다.
function workerBlobUrl() {
  const target = new URL("worker.js?v=fc29497b", location.href).href;
  const shim = "import " + JSON.stringify(target) + ";";
  return URL.createObjectURL(new Blob([shim], { type: "text/javascript" }));
}

class Engine {
  constructor(onStatus) {
    this.worker = null;
    this.blobUrl = null;
    this.failure = null;
    this.onStatus = onStatus || (() => {});
    this.pending = new Map();
    this.nextId = 1;
    // 워치독이 "어디까지 갔는지" 를 말할 수 있게 마지막 단계를 들고 있는다
    this.lastStatus = "";
  }

  _spawn() {
    this.blobUrl = workerBlobUrl();
    this.worker = new Worker(this.blobUrl, { type: "module" });
    this.worker.onmessage = (ev) => {
      const msg = ev.data;
      if (msg.type === "status") {
        if (msg.text) this.lastStatus = msg.text;
        this.onStatus(msg.text);
        return;
      }
      if (msg.type === "fatal") { this._die(new Error(msg.error)); return; }
      const slot = this.pending.get(msg.id);
      if (!slot) return;
      this.pending.delete(msg.id);
      if (msg.ok) slot.resolve(msg);
      else slot.reject(new Error(msg.error));
    };
    this.worker.onerror = (ev) => {
      // 모듈 worker 의 로드/파싱 실패는 message 가 비어 온다. 있는 것을 다 모은다
      const where = [ev && ev.filename, ev && ev.lineno].filter(Boolean).join(":");
      this._die(new Error(
        (ev && ev.message) ||
        ("Could not load the worker" + (where ? " (" + where + ")" : ""))
      ));
    };
  }

  /** worker 가 죽었다. 기다리는 요청을 전부 깨우고 다시 못 쓰게 표시한다. */
  _die(err) {
    this.failure = err;
    if (this.worker) { this.worker.terminate(); this.worker = null; }
    this._dropBlob();
    for (const slot of this.pending.values()) slot.reject(err);
    this.pending.clear();
  }

  /** blob URL 을 거둔다.
   *
   * 만들자마자 거두면 worker 가 아직 못 받아 갔을 수 있다 (스펙상 경합이다).
   * 부팅 악수가 끝났으면 이미 받아 간 것이 확실하다.
   */
  _dropBlob() {
    if (this.blobUrl) { URL.revokeObjectURL(this.blobUrl); this.blobUrl = null; }
  }

  _send(payload, transfer) {
    // 죽은 worker 에 보내면 답이 영영 안 온다. 기다리지 않고 바로 알린다
    if (!this.worker) {
      return Promise.reject(this.failure || new Error("The engine is not running"));
    }
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.worker.postMessage({ ...payload, id }, transfer || []);
    });
  }

  async boot() {
    this.failure = null;
    this.lastStatus = "";
    this._spawn();
    // 답이 없는 채로 오래 지나면 그 사실 자체를 화면에 띄운다. 부팅이 끝나면
    // worker 가 빈 status 를 보내 이 글이 덮인다
    const watchdog = setTimeout(() => {
      this.onStatus(
        "The engine has not answered in " + Math.round(BOOT_SILENCE_MS / 1000) +
        "s" + (this.lastStatus ? " (last step: " + this.lastStatus + ")" : "") +
        ". It may still be loading — check the browser console for errors."
      );
    }, BOOT_SILENCE_MS);
    try {
      await this._send({ type: "boot" });
      this._dropBlob();
    } catch (e) {
      this._die(e);   // 다음 요청이 매달리지 않게 한다
      throw e;
    } finally {
      clearTimeout(watchdog);
    }
  }

  get ready() {
    return this.worker !== null && this.failure === null;
  }

  /** 무한 루프에 빠진 정의를 죽인다. 메인 스레드에서는 할 수 없는 일이다. */
  stop() {
    if (!this.worker) return;
    this._die(new Error("Stopped"));
  }

  get running() {
    return this.pending.size > 0;
  }

  /** 축 집합 하나를 정의에 끼워 넣은 새 소스 (§19.9). */
  async addAxisSet(source, factory) {
    return (await this._send({ type: "addAxisSet", source, factory })).result;
  }

  /** 축 집합과 그것을 쓰는 코드를 지운 새 소스 (§19.9). */
  async removeAxisSet(source, setId) {
    return (await this._send({ type: "removeAxisSet", source, setId })).result;
  }

  /** 축 집합을 만드는 식을 op(...) 로 감싼 새 소스 (§19.12). */
  async axisOp(source, setId, op) {
    return (await this._send({ type: "axisOp", source, setId, op })).result;
  }

  async prepare(source) {
    return (await this._send({ type: "prepare", source })).result;
  }

  /** 축 마커만 담은 장면. 편집 모드의 무대다 (§19.15).
   *
   * 소스를 넘긴다 — 편집창을 고치는 동안 마커가 따라 움직여야 하는데,
   * 마지막 `Run` 이 재 둔 것을 쓰면 눌러야만 갱신된다. 축 집합 목록도 같이
   * 온다: 같은 실행에서 나온 것이라 어긋날 수 없다.
   */
  async axisScene(source) {
    const msg = await this._send({ type: "axisScene", source });
    const out = msg.result;
    return {
      scene: {
        xyz: new Float64Array(msg.buffer),
        starts: out.starts, counts: out.counts,
        groups: out.groups, kinds: out.kinds,
        labels: out.labels, axisSets: out.axisSets,
      },
      sets: out.sets,
    };
  }

  async evaluate(angles, maxStep) {
    const msg = await this._send({ type: "evaluate", angles, maxStep });
    const out = msg.result;
    return {
      scene: {
        // 버퍼가 transfer 로 넘어왔다. 복사 없이 그대로 감싼다 (§11.1)
        xyz: new Float64Array(msg.buffer),
        starts: out.starts, counts: out.counts,
        groups: out.groups, kinds: out.kinds,
        labels: out.labels, axisSets: out.axisSets,
      },
      carriers: out.carriers, length: out.length, note: out.note,
    };
  }
}

window.Engine = Engine;
