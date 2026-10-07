/* ===== EFFECTS: huruf ransom, partikel, getar, flash, tilt 3D, ketikan, ticker ===== */
window.P5FX = (function () {
  const $ = (s, r = document) => r.querySelector(s);
  const colors = ['#d6001c', '#ffffff', '#ffe500', '#000000', '#ff3b57'];

  /* Pecah teks jadi huruf-huruf bergaya ransom note */
  function buildRansom() {
    document.querySelectorAll('[data-ransom]').forEach(el => {
      el.textContent = '';
      [...el.dataset.ransom].forEach((ch, i) => {
        const s = document.createElement('span');
        s.textContent = ch === ' ' ? '\u00A0' : ch;
        s.style.setProperty('--i', i);
        s.setAttribute('aria-hidden', 'true');
        el.appendChild(s);
      });
    });
  }

  /* Bintang melayang di latar */
  function buildStars(n) {
    const box = $('#stars'), glyphs = ['★', '✦', '◆', '▲'];
    for (let i = 0; i < n; i++) {
      const s = document.createElement('i');
      s.textContent = glyphs[i % glyphs.length];
      s.style.left = Math.random() * 100 + '%';
      s.style.fontSize = 14 + Math.random() * 30 + 'px';
      s.style.animationDuration = 14 + Math.random() * 18 + 's';
      s.style.animationDelay = -Math.random() * 30 + 's';
      box.appendChild(s);
    }
  }

  /* Teks berjalan: isi track dengan konten digandakan agar loop mulus */
  function buildTickers(data) {
    document.querySelectorAll('[data-ticker]').forEach(track => {
      const words = data[track.dataset.ticker] || [];
      const once = words.map(w => `<span>${w}</span><span>★</span>`).join('');
      track.innerHTML = once.repeat(4) + once.repeat(4);
    });
  }

  /* Efek ketik bergantian */
  function typewriter(el, words) {
    if (!el || !words.length) return;
    let w = 0, i = 0, del = false;
    (function tick() {
      const word = words[w];
      el.textContent = word.slice(0, i);
      let wait = del ? 35 : 75;
      if (!del && i === word.length) { del = true; wait = 1400; }
      else if (del && i === 0) { del = false; w = (w + 1) % words.length; wait = 350; }
      else i += del ? -1 : 1;
      setTimeout(tick, wait);
    })();
  }

  /* Ledakan kepingan + ring di titik klik */
  function burst(x, y) {
    const fx = $('#fx');
    const ring = document.createElement('div');
    ring.className = 'ring';
    ring.style.left = x + 'px'; ring.style.top = y + 'px';
    fx.appendChild(ring);
    setTimeout(() => ring.remove(), 600);

    for (let i = 0; i < 14; i++) {
      const a = Math.random() * Math.PI * 2, d = 60 + Math.random() * 110;
      const p = document.createElement('b');
      p.className = 'shard';
      p.style.cssText = `--x:${x}px;--y:${y}px;--dx:${Math.cos(a) * d}px;--dy:${Math.sin(a) * d}px;` +
        `--r:${Math.random() * 720 - 360}deg;--s:${10 + Math.random() * 22}px;--c:${colors[i % colors.length]}`;
      fx.appendChild(p);
      setTimeout(() => p.remove(), 700);
    }
  }

  function restart(el, cls, ms) {
    el.classList.remove(cls); void el.offsetWidth; el.classList.add(cls);
    setTimeout(() => el.classList.remove(cls), ms);
  }
  const flash = () => restart($('#flash'), 'go', 250);
  const shake = () => restart($('#app'), 'shake', 420);
  const pop   = el => restart(el, 'pressed', 400);

  /* Kemiringan 3D mengikuti kursor */
  function initTilt() {
    let cur = null;
    const reset = el => { el.style.setProperty('--rx', '0deg'); el.style.setProperty('--ry', '0deg'); };
    document.addEventListener('pointermove', e => {
      if (e.pointerType !== 'mouse') return;
      const el = e.target.closest('.tilt');
      if (cur && cur !== el) reset(cur);
      cur = el;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width - 0.5, py = (e.clientY - r.top) / r.height - 0.5;
      el.style.setProperty('--ry', (px * 16).toFixed(2) + 'deg');
      el.style.setProperty('--rx', (-py * 16).toFixed(2) + 'deg');
    });
    document.addEventListener('pointerleave', e => { if (cur && e.target === cur) { reset(cur); cur = null; } }, true);
  }

  return { buildRansom, buildStars, buildTickers, typewriter, burst, flash, shake, pop, initTilt };
})();
