/**
 * Gráficos en SVG, escritos a mano.
 *
 * Sin librería externa: la página no carga nada de una CDN, así que la
 * plataforma funciona en una máquina sin internet. Los colores salen de las
 * variables CSS, de modo que el tema claro y el oscuro se resuelven solos.
 */
const NS = 'http://www.w3.org/2000/svg';

function svgEl(tag, attrs = {}) {
  const n = document.createElementNS(NS, tag);
  Object.entries(attrs).forEach(([k, v]) => { if (v != null) n.setAttribute(k, v); });
  return n;
}

function frame(width, height, title) {
  const box = document.createElement('div');
  box.className = 'chart-box';
  if (title) {
    const h = document.createElement('div');
    h.className = 'chart-title';
    h.textContent = title;
    box.appendChild(h);
  }
  const svg = svgEl('svg', {
    class: 'chart', viewBox: `0 0 ${width} ${height}`,
    preserveAspectRatio: 'xMidYMid meet', role: 'img',
  });
  box.appendChild(svg);
  return { box, svg };
}

const PAD = { t: 12, r: 16, b: 30, l: 48 };

function scales(xs, ys, w, h, pad = PAD, opts = {}) {
  const xmin = opts.xmin ?? Math.min(...xs);
  const xmax = opts.xmax ?? Math.max(...xs);
  const ymin = opts.ymin ?? Math.min(0, Math.min(...ys));
  const ymax = opts.ymax ?? Math.max(...ys);
  const dx = xmax - xmin || 1;
  const dy = ymax - ymin || 1;
  return {
    x: (v) => pad.l + ((v - xmin) / dx) * (w - pad.l - pad.r),
    y: (v) => h - pad.b - ((v - ymin) / dy) * (h - pad.t - pad.b),
    xmin, xmax, ymin, ymax,
  };
}

function axes(svg, s, w, h, { xTicks = 5, yTicks = 4, fmtX = (v) => v, fmtY = (v) => v, pad = PAD } = {}) {
  for (let i = 0; i <= yTicks; i += 1) {
    const v = s.ymin + ((s.ymax - s.ymin) * i) / yTicks;
    const y = s.y(v);
    svg.appendChild(svgEl('line', { class: 'grid-line', x1: pad.l, x2: w - pad.r, y1: y, y2: y }));
    const label = svgEl('text', { x: pad.l - 7, y: y + 3.5, 'text-anchor': 'end' });
    label.textContent = fmtY(v);
    svg.appendChild(label);
  }
  for (let i = 0; i <= xTicks; i += 1) {
    const v = s.xmin + ((s.xmax - s.xmin) * i) / xTicks;
    const label = svgEl('text', { x: s.x(v), y: h - pad.b + 15, 'text-anchor': 'middle' });
    label.textContent = fmtX(v);
    svg.appendChild(label);
  }
  svg.appendChild(svgEl('line', { class: 'axis-line', x1: pad.l, x2: w - pad.r, y1: h - pad.b, y2: h - pad.b, stroke: 'var(--border-strong)' }));
}

function path(points, s) {
  return points.map((p, i) => `${i ? 'L' : 'M'}${s.x(p[0]).toFixed(2)},${s.y(p[1]).toFixed(2)}`).join(' ');
}

/* ── línea (una o dos series) ────────────────────────────────────────────── */
export function line(series, { title, width = 520, height = 240, fmtX, fmtY, diagonal = false,
  xmin, xmax, ymin, ymax, labels = [] } = {}) {
  const { box, svg } = frame(width, height, title);
  const all = series.flat();
  if (!all.length) return box;
  const s = scales(all.map((p) => p[0]), all.map((p) => p[1]), width, height, PAD,
    { xmin, xmax, ymin, ymax });
  axes(svg, s, width, height, { fmtX: fmtX || ((v) => v.toFixed(1)), fmtY: fmtY || ((v) => v.toFixed(2)) });
  if (diagonal) {
    svg.appendChild(svgEl('line', {
      x1: s.x(s.xmin), y1: s.y(s.ymin), x2: s.x(s.xmax), y2: s.y(s.ymax),
      stroke: 'var(--border-strong)', 'stroke-dasharray': '4 4',
    }));
  }
  series.forEach((pts, i) => {
    if (!pts.length) return;
    svg.appendChild(svgEl('path', { class: i === 0 ? 'series-1' : 'series-2', d: path(pts, s) }));
  });
  if (labels.length) legend(box, labels);
  return box;
}

/* ── barras verticales ───────────────────────────────────────────────────── */
export function bars(items, { title, width = 520, height = 240, fmtY, valueKey = 'value',
  labelKey = 'label', second = null } = {}) {
  const { box, svg } = frame(width, height, title);
  if (!items.length) return box;
  const values = items.map((d) => Number(d[valueKey]) || 0)
    .concat(second ? items.map((d) => Number(d[second]) || 0) : []);
  const s = scales([0, items.length], values, width, height, PAD, { xmin: 0, xmax: items.length });
  axes(svg, s, width, height, { xTicks: Math.min(items.length, 10), fmtX: () => '', fmtY: fmtY || ((v) => v.toFixed(1)) });
  const bw = (width - PAD.l - PAD.r) / items.length;
  const inner = second ? bw * 0.36 : bw * 0.66;
  items.forEach((d, i) => {
    const v = Number(d[valueKey]) || 0;
    const x = s.x(i) + (bw - (second ? inner * 2 + 3 : inner)) / 2;
    const y = s.y(Math.max(v, s.ymin));
    svg.appendChild(svgEl('rect', {
      class: 'bar', x, y: Math.min(y, s.y(0)), width: inner,
      height: Math.max(Math.abs(s.y(0) - y), 1), rx: 2,
    }));
    if (second) {
      const v2 = Number(d[second]) || 0;
      const y2 = s.y(Math.max(v2, s.ymin));
      svg.appendChild(svgEl('rect', {
        class: 'bar-2', x: x + inner + 3, y: Math.min(y2, s.y(0)), width: inner,
        height: Math.max(Math.abs(s.y(0) - y2), 1), rx: 2, opacity: 0.65,
      }));
    }
    const lbl = svgEl('text', { x: s.x(i) + bw / 2, y: height - PAD.b + 15, 'text-anchor': 'middle' });
    lbl.textContent = String(d[labelKey]).slice(0, 8);
    svg.appendChild(lbl);
  });
  return box;
}

/* ── barras horizontales (ranking de variables) ──────────────────────────── */
export function hbars(items, { title, width = 520, rowHeight = 24, fmt = (v) => v.toFixed(3),
  labelKey = 'label', valueKey = 'value', maxItems = 15 } = {}) {
  const data = items.slice(0, maxItems);
  const height = Math.max(data.length * rowHeight + 16, 60);
  const { box, svg } = frame(width, height, title);
  if (!data.length) return box;
  const max = Math.max(...data.map((d) => Math.abs(Number(d[valueKey]) || 0)), 1e-9);
  const labelW = 150;
  data.forEach((d, i) => {
    const y = i * rowHeight + 8;
    const v = Math.abs(Number(d[valueKey]) || 0);
    const w = ((width - labelW - 62) * v) / max;
    const lbl = svgEl('text', { x: labelW - 8, y: y + rowHeight * 0.62, 'text-anchor': 'end' });
    lbl.textContent = String(d[labelKey]).slice(0, 24);
    svg.appendChild(lbl);
    svg.appendChild(svgEl('rect', {
      class: 'bar', x: labelW, y: y + 4, width: Math.max(w, 1),
      height: rowHeight - 11, rx: 2,
    }));
    const val = svgEl('text', { x: labelW + Math.max(w, 1) + 7, y: y + rowHeight * 0.62 });
    val.textContent = fmt(Number(d[valueKey]) || 0);
    svg.appendChild(val);
  });
  return box;
}

/* ── histograma ──────────────────────────────────────────────────────────── */
export function histogram(bins, { title, width = 520, height = 180, fmtX } = {}) {
  const items = bins.map((b) => ({
    label: fmtX ? fmtX(b.from) : Number(b.from).toPrecision(3),
    value: b.count,
  }));
  return bars(items, { title, width, height, fmtY: (v) => Math.round(v) });
}

/* ── dispersión ──────────────────────────────────────────────────────────── */
export function scatter(points, { title, width = 520, height = 260, fmtX, fmtY, diagonal = true } = {}) {
  const { box, svg } = frame(width, height, title);
  if (!points.length) return box;
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  const lo = Math.min(...xs, ...ys);
  const hi = Math.max(...xs, ...ys);
  const s = scales(xs, ys, width, height, PAD, { xmin: lo, xmax: hi, ymin: lo, ymax: hi });
  axes(svg, s, width, height, {
    fmtX: fmtX || ((v) => v.toPrecision(3)), fmtY: fmtY || ((v) => v.toPrecision(3)),
  });
  if (diagonal) {
    svg.appendChild(svgEl('line', {
      x1: s.x(lo), y1: s.y(lo), x2: s.x(hi), y2: s.y(hi),
      stroke: 'var(--border-strong)', 'stroke-dasharray': '4 4',
    }));
  }
  points.forEach(([x, y]) => {
    svg.appendChild(svgEl('circle', { class: 'dot', cx: s.x(x), cy: s.y(y), r: 2.1 }));
  });
  return box;
}

/* ── matriz de correlación ───────────────────────────────────────────────── */
export function heatmap(labels, matrix, { title, width = 520, cell = 26 } = {}) {
  const n = labels.length;
  const CHAR = 6.1;                       // ancho aproximado de carácter a 11 px
  const corto = (s) => (String(s).length > 20 ? `${String(s).slice(0, 19)}…` : String(s));
  const largoMax = Math.max(...labels.map((l) => corto(l).length), 1);

  // El eje de la izquierda y el de arriba se dimensionan según el texto real.
  // Las etiquetas de arriba van rotadas y ancladas por el principio: si se
  // anclan por el final, se meten sobre el eje de la izquierda y sobre la
  // propia matriz, que es lo que pasaba antes.
  const labelW = Math.min(190, Math.max(70, largoMax * CHAR + 10));
  const size = Math.min(cell, Math.max(12, (width - labelW - 24) / Math.max(n, 1)));

  // EL ÁNGULO SALE DEL ESPACIO QUE HAY, no al revés.
  //
  // Estaba fijo en 45°, y entre dos etiquetas contiguas sólo hay `size` de
  // paso horizontal — o sea size·sin(45°) = 0.71·size de separación
  // perpendicular. Con la celda por defecto (26) son 18.4 u para un texto de
  // 12.4 u de alto: entra justo. Pero `size` baja hasta 12 cuando crecen las
  // columnas, y ahí quedan 8.5 u para el mismo texto: se pisan sin remedio.
  //
  // Ahora el ángulo se abre hasta donde haga falta, con tope en 90° (vertical),
  // que es lo que usan los heatmaps densos justamente porque no puede
  // solaparse. Se pide 1.45× el cuerpo de letra y no 1.18× (el alto real,
  // medido en el navegador) para dejar aire entre etiqueta y etiqueta: pegadas
  // sin tocarse se leen igual de mal.
  const ALTO_TEXTO = 1.18;                 // alto real del glifo / cuerpo, medido
  const fs = Math.max(8, Math.min(10.5, size * 0.8));
  const seno = Math.min(1, (fs * 1.45) / Math.max(size, 1));
  const ang = Math.max(45, Math.asin(seno) * 180 / Math.PI);
  const rad = (ang * Math.PI) / 180;

  // El largo del texto se proyecta sobre los dos ejes según el ángulo elegido:
  // cuanto más vertical, más alto necesita arriba y menos se desborda a la
  // derecha. Con 45° fijo esto estaba escrito a mano como 0.72 y dejaba de
  // valer apenas cambiaba el ángulo.
  const largoTexto = largoMax * (CHAR * fs / 11);
  const topH = Math.round(largoTexto * Math.sin(rad)) + ALTO_TEXTO * fs;
  const desborde = largoTexto * Math.cos(rad);
  const height = topH + n * size + 14;

  // El lienzo mide lo que ocupa el gráfico, NO el `width` pedido. Antes era
  // max(width, …), así que una matriz de cinco columnas —que necesita ~330 u—
  // reservaba igual las 640 del ancho por defecto: el SVG se estira al panel
  // con width:100%, y el dibujo quedaba apretado contra el borde izquierdo con
  // más de la mitad del panel vacío. Se ve en la captura del video.
  const ancho = Math.ceil(labelW + n * size + desborde + 12);

  const { box, svg } = frame(ancho, height, title);

  // Tope de estirado. `.chart { width: 100% }` estira el SVG a lo que mida el
  // panel, y al sacar el piso de 640 u una matriz chica pasaba a escalarse
  // 3.7×: celdas enormes y etiquetas de 39 px. Se limita por lo único que
  // importa para leerlo — que la etiqueta no pase de 16 px — en vez de por un
  // ancho fijo, que es lo que había traído el hueco a la derecha.
  box.style.maxWidth = `${Math.round(ancho * (16 / fs))}px`;

  labels.forEach((lb, i) => {
    const y = topH + i * size;
    // El cuerpo va por `style` y no por el atributo `font-size`: app.css tiene
    // `.chart text { font-size: 10.5px }`, y una regla CSS le gana SIEMPRE a un
    // atributo de presentación. Con el atributo, todo el cálculo de arriba se
    // hacía contra un tamaño que después no era el que se dibujaba.
    const izq = svgEl('text', {
      x: labelW - 7, y: y + size * 0.68, 'text-anchor': 'end',
      style: `font-size:${fs.toFixed(2)}px`,
    });
    izq.textContent = corto(lb);
    izq.appendChild(svgEl('title')).textContent = String(lb);
    svg.appendChild(izq);

    // Se ancla en el CENTRO de la columna (no en 0.62 del borde): con el
    // ángulo variable, un desfase fijo corre todas las etiquetas respecto de
    // su columna y a 90° se nota que no coinciden con la celda que nombran.
    const cx = labelW + i * size + size / 2;
    const arriba = svgEl('text', {
      x: cx, y: topH - 5, 'text-anchor': 'start',
      style: `font-size:${fs.toFixed(2)}px`,
      transform: `rotate(${-ang} ${cx} ${topH - 5})`,
    });
    arriba.textContent = corto(lb);
    arriba.appendChild(svgEl('title')).textContent = String(lb);
    svg.appendChild(arriba);

    matrix[i].forEach((v, j) => {
      const a = Math.min(Math.abs(v), 1);
      const color = v >= 0 ? 'var(--accent)' : 'var(--bad)';
      const rect = svgEl('rect', {
        x: labelW + j * size, y, width: size - 1.5, height: size - 1.5, rx: 2,
        fill: color, opacity: (0.10 + a * 0.85).toFixed(3),
      });
      rect.appendChild(svgEl('title')).textContent = `${labels[i]} · ${labels[j]}: ${v.toFixed(3)}`;
      svg.appendChild(rect);
      if (size >= 30 && i !== j) {           // el número entra sólo si hay lugar
        const num = svgEl('text', {
          x: labelW + j * size + (size - 1.5) / 2, y: y + size * 0.63,
          'text-anchor': 'middle', 'font-size': 9.5,
          fill: a > 0.55 ? '#fff' : 'var(--text-3)',
        });
        num.textContent = v.toFixed(2).replace('0.', '.').replace('-.', '−.');
        svg.appendChild(num);
      }
    });
  });
  return box;
}

/* ── medidor ─────────────────────────────────────────────────────────────── */
export function gauge(value, { title, width = 220, height = 130, max = 100, label = '', kind = '' } = {}) {
  const { box, svg } = frame(width, height, title);
  const cx = width / 2;
  const cy = height - 18;
  const r = Math.min(width / 2 - 14, height - 34);
  const arc = (from, to, color, w) => {
    const a0 = Math.PI * (1 + from);
    const a1 = Math.PI * (1 + to);
    const large = to - from > 0.5 ? 1 : 0;
    return svgEl('path', {
      d: `M${(cx + r * Math.cos(a0)).toFixed(2)},${(cy + r * Math.sin(a0)).toFixed(2)} `
       + `A${r},${r} 0 ${large} 1 ${(cx + r * Math.cos(a1)).toFixed(2)},${(cy + r * Math.sin(a1)).toFixed(2)}`,
      fill: 'none', stroke: color, 'stroke-width': w, 'stroke-linecap': 'round',
    });
  };
  svg.appendChild(arc(0, 1, 'var(--surface-3)', 11));
  const frac = Math.max(0, Math.min(1, value / max));
  const color = kind === 'bad' ? 'var(--bad)' : (kind === 'warn' ? 'var(--warn)' : (kind === 'ok' ? 'var(--ok)' : 'var(--accent)'));
  if (frac > 0.001) svg.appendChild(arc(0, frac, color, 11));
  const v = svgEl('text', {
    x: cx, y: cy - 8, 'text-anchor': 'middle',
    style: 'font-size:26px;font-weight:650;fill:var(--text)',
  });
  v.textContent = String(Math.round(value));
  svg.appendChild(v);
  if (label) {
    const l = svgEl('text', { x: cx, y: cy + 12, 'text-anchor': 'middle' });
    l.textContent = label;
    svg.appendChild(l);
  }
  return box;
}

/* ── leyenda ─────────────────────────────────────────────────────────────── */
function legend(box, labels) {
  const row = document.createElement('div');
  row.className = 'row row-tight small muted';
  row.style.marginTop = '8px';
  labels.forEach((lb, i) => {
    const chip = document.createElement('span');
    chip.className = 'row row-tight';
    const dot = document.createElement('span');
    dot.style.cssText = `width:14px;height:2.5px;border-radius:2px;display:inline-block;background:${
      i === 0 ? 'var(--accent)' : 'var(--text-3)'}`;
    chip.appendChild(dot);
    chip.appendChild(document.createTextNode(` ${lb}`));
    row.appendChild(chip);
  });
  box.appendChild(row);
}
