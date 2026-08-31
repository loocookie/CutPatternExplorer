// worker 와 주고받는 쪽. 설계 문서 §19.5.
//
// 정의는 worker 안에서만 돈다 (web/worker.js). 여기서는 요청을 보내고 결과
// 데이터를 받을 뿐이라, 남이 쓴 코드가 이 스레드의 DOM 에 닿지 않는다.
//
// 덤으로 평가가 UI 를 멈추지 않는다. 메인 스레드에서 돌 때는 슬라이더를 미는
// 동안 평가 시간만큼 드래그가 끊겼다.

"use strict";

class Engine {
  constructor(onStatus) {
    this.worker = null;
    this.failure = null;
    this.onStatus = onStatus || (() => {});
    this.pending = new Map();
    this.nextId = 1;
  }

  _spawn() {
    this.worker = new Worker("worker.js", { type: "module" });
    this.worker.onmessage = (ev) => {
      const msg = ev.data;
      if (msg.type === "status") { this.onStatus(msg.text); return; }
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
    for (const slot of this.pending.values()) slot.reject(err);
    this.pending.clear();
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
    this._spawn();
    try {
      await this._send({ type: "boot" });
    } catch (e) {
      this._die(e);   // 다음 요청이 매달리지 않게 한다
      throw e;
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

  async prepare(source) {
    return (await this._send({ type: "prepare", source })).result;
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
