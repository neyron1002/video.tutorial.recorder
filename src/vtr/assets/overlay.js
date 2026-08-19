// Capa visual del recorder: puntero simulado, ondas de clic, resaltados y
// carteles. Se inyecta en cada navegación mediante add_init_script, así que
// debe ser idempotente y tolerar que el <body> aún no exista.
(() => {
  if (window.__vtr) return;

  const cfg = window.__vtrConfig || {};
  const state = { root: null, cursor: null, timers: new Set(), bound: false };

  const CSS = `
    #__vtr_layer { position: fixed; inset: 0; pointer-events: none; z-index: 2147483646; }
    #__vtr_layer * { box-sizing: border-box; font-family: -apple-system, "Segoe UI", Roboto, "Noto Sans", sans-serif; }
    .__vtr_hl {
      position: fixed; border: 3px solid var(--vtr-c, #ff3d71); border-radius: 8px;
      box-shadow: 0 0 0 3px rgba(255,255,255,.55), 0 8px 28px rgba(0,0,0,.28);
      animation: __vtr_pulse 1.4s ease-in-out infinite; transition: opacity .25s ease;
    }
    .__vtr_hl_label {
      position: fixed; background: var(--vtr-c, #ff3d71); color: #fff; font-size: 15px;
      font-weight: 600; padding: 5px 11px; border-radius: 6px; white-space: nowrap;
      box-shadow: 0 4px 14px rgba(0,0,0,.3);
    }
    @keyframes __vtr_pulse { 0%,100% { opacity: 1 } 50% { opacity: .55 } }
    .__vtr_note {
      position: fixed; max-width: 46ch; background: rgba(17,20,28,.94); color: #fff;
      font-size: 19px; line-height: 1.45; padding: 14px 20px; border-radius: 12px;
      box-shadow: 0 12px 40px rgba(0,0,0,.45); border-left: 5px solid #ffd166;
      opacity: 0; transform: translateY(10px); transition: opacity .3s ease, transform .3s ease;
    }
    .__vtr_note.__vtr_in { opacity: 1; transform: translateY(0); }
    .__vtr_ripple {
      position: fixed; width: 12px; height: 12px; margin: -6px 0 0 -6px; border-radius: 50%;
      background: rgba(255,61,113,.45); border: 2px solid rgba(255,61,113,.9);
      animation: __vtr_ripple .55s ease-out forwards;
    }
    @keyframes __vtr_ripple { to { width: 66px; height: 66px; margin: -33px 0 0 -33px; opacity: 0 } }
    #__vtr_cursor {
      position: fixed; width: 26px; height: 26px; margin: -3px 0 0 -3px;
      transition: transform .12s linear; will-change: transform;
      filter: drop-shadow(0 2px 3px rgba(0,0,0,.5));
    }
  `;

  const ensureLayer = () => {
    const host = document.body || document.documentElement;
    if (!host) return null;
    if (state.root && host.contains(state.root)) return state.root;
    if (!document.getElementById('__vtr_style')) {
      const style = document.createElement('style');
      style.id = '__vtr_style';
      style.textContent = CSS;
      (document.head || host).appendChild(style);
    }
    const layer = document.createElement('div');
    layer.id = '__vtr_layer';
    host.appendChild(layer);
    state.root = layer;
    state.cursor = null;
    return layer;
  };

  const after = (ms, fn) => {
    const id = setTimeout(() => { state.timers.delete(id); fn(); }, ms);
    state.timers.add(id);
    return id;
  };

  const fade = (el, ms) => {
    if (!el) return;
    after(Math.max(0, ms - 300), () => { el.style.opacity = '0'; });
    after(ms, () => el.remove());
  };

  const api = {
    /** Marco animado alrededor de un rectángulo (coordenadas de viewport). */
    highlight(box, opts) {
      const o = opts || {};
      const layer = ensureLayer();
      if (!layer || !box) return;
      const pad = o.padding == null ? 6 : o.padding;
      const el = document.createElement('div');
      el.className = '__vtr_hl';
      el.style.setProperty('--vtr-c', o.color || '#ff3d71');
      el.style.left = (box.x - pad) + 'px';
      el.style.top = (box.y - pad) + 'px';
      el.style.width = (box.width + pad * 2) + 'px';
      el.style.height = (box.height + pad * 2) + 'px';
      layer.appendChild(el);
      let label = null;
      if (o.label) {
        label = document.createElement('div');
        label.className = '__vtr_hl_label';
        label.style.setProperty('--vtr-c', o.color || '#ff3d71');
        label.textContent = o.label;
        const above = box.y - pad > 40;
        label.style.left = Math.max(8, box.x - pad) + 'px';
        label.style.top = (above ? box.y - pad - 34 : box.y + box.height + pad + 8) + 'px';
        layer.appendChild(label);
      }
      const ms = (o.duration == null ? 3 : o.duration) * 1000;
      fade(el, ms);
      fade(label, ms);
    },

    /** Cartel de texto, anclado a un rectángulo o a una posición fija. */
    note(text, opts) {
      const o = opts || {};
      const layer = ensureLayer();
      if (!layer) return;
      const el = document.createElement('div');
      el.className = '__vtr_note';
      el.textContent = text;
      layer.appendChild(el);
      const w = el.offsetWidth, h = el.offsetHeight;
      const vw = window.innerWidth, vh = window.innerHeight;
      let left, top;
      if (o.box) {
        left = Math.min(Math.max(12, o.box.x), vw - w - 12);
        top = o.box.y + o.box.height + 16;
        if (top + h > vh - 12) top = Math.max(12, o.box.y - h - 16);
      } else {
        const pos = o.position || 'bottom';
        const isTop = pos.startsWith('top');
        const isCenter = pos === 'center';
        top = isCenter ? (vh - h) / 2 : (isTop ? 28 : vh - h - 36);
        if (pos.endsWith('-left')) left = 28;
        else if (pos.endsWith('-right')) left = vw - w - 28;
        else left = (vw - w) / 2;
      }
      el.style.left = Math.round(left) + 'px';
      el.style.top = Math.round(top) + 'px';
      requestAnimationFrame(() => el.classList.add('__vtr_in'));
      fade(el, (o.duration == null ? 4 : o.duration) * 1000);
    },

    ripple(x, y) {
      const layer = ensureLayer();
      if (!layer) return;
      const el = document.createElement('div');
      el.className = '__vtr_ripple';
      el.style.left = x + 'px';
      el.style.top = y + 'px';
      layer.appendChild(el);
      after(600, () => el.remove());
    },

    /** Puntero dibujado que sigue los eventos reales del ratón. */
    enableCursor() {
      const layer = ensureLayer();
      if (!layer) return;
      if (!state.cursor || !layer.contains(state.cursor)) {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('id', '__vtr_cursor');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.innerHTML =
          '<path d="M5 2.5 L18.5 12.2 L12.1 12.9 L15.4 19.8 L12.6 21 L9.3 14.1 L5 18 Z"' +
          ' fill="#fff" stroke="#16181d" stroke-width="1.4" stroke-linejoin="round"/>';
        layer.appendChild(svg);
        state.cursor = svg;
        svg.style.transform = 'translate(-100px, -100px)';
      }
      if (state.bound) return;
      state.bound = true;
      const move = (e) => {
        if (state.cursor) state.cursor.style.transform = `translate(${e.clientX}px, ${e.clientY}px)`;
      };
      document.addEventListener('mousemove', move, true);
      document.addEventListener('mousedown', (e) => { move(e); api.ripple(e.clientX, e.clientY); }, true);
    },

    clear() {
      state.timers.forEach(clearTimeout);
      state.timers.clear();
      if (state.root) {
        state.root.querySelectorAll('.__vtr_hl, .__vtr_hl_label, .__vtr_note, .__vtr_ripple')
          .forEach((el) => el.remove());
      }
    },

    /** Métricas de la ventana, para recortar el cromo del navegador. */
    metrics() {
      return {
        chromeHeight: Math.max(0, window.outerHeight - window.innerHeight),
        innerWidth: window.innerWidth,
        innerHeight: window.innerHeight,
        dpr: window.devicePixelRatio || 1,
      };
    },
  };

  window.__vtr = api;
  const boot = () => { ensureLayer(); if (cfg.cursor) api.enableCursor(); };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
