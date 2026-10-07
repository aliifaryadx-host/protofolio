/* ===== AUDIO: efek suara sintetis (tanpa file audio) ===== */
window.P5Audio = (function () {
  let ctx = null, on = true;

  function c() {
    if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === 'suspended') ctx.resume();
    return ctx;
  }

  // helper: satu nada dengan sapuan frekuensi
  function tone(type, f0, f1, dur, vol, delay) {
    if (!on) return;
    try {
      const a = c(), t = a.currentTime + (delay || 0);
      const o = a.createOscillator(), g = a.createGain();
      o.type = type;
      o.frequency.setValueAtTime(f0, t);
      o.frequency.exponentialRampToValueAtTime(f1, t + dur);
      g.gain.setValueAtTime(vol, t);
      g.gain.exponentialRampToValueAtTime(0.001, t + dur);
      o.connect(g); g.connect(a.destination);
      o.start(t); o.stop(t + dur);
    } catch (e) {}
  }

  return {
    hover()  { tone('triangle', 440, 880, 0.05, 0.07); },
    select() { tone('sine', 150, 30, 0.25, 0.3); tone('sawtooth', 800, 200, 0.15, 0.18); },
    whoosh() { tone('sawtooth', 120, 1400, 0.35, 0.07); },
    start()  {
      tone('sine', 120, 25, 0.5, 0.4);
      tone('square', 330, 330, 0.09, 0.08, 0.02);
      tone('square', 495, 495, 0.09, 0.08, 0.10);
      tone('square', 660, 660, 0.22, 0.09, 0.18);
    },
    toggle() { on = !on; return on; },
    isOn()   { return on; },
    unlock() { try { c(); } catch (e) {} }
  };
})();
