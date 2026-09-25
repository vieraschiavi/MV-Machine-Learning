#!/usr/bin/env node
/**
 * Genera la guía del programa en Word (.docx) y en HTML desde `contenido.js`.
 *
 *   npm install docx@9      # una vez, en cualquier carpeta del NODE_PATH
 *   node docs/presentacion/generar.js [carpeta-de-salida] [--pagina]
 *
 * Sin carpeta escribe al lado de este archivo. `--pagina` suma una copia del HTML
 * sin <html>/<head>, para publicarla dentro de otra página. El HTML es autocontenido
 * (estilos y script adentro); sólo pide tipografías a Google Fonts y, sin red,
 * cae a las del sistema.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { META, KPIS, SECCIONES, CIERRE } = require('./contenido');

const ARGS = process.argv.slice(2);
const SALIDA = path.resolve(ARGS.find((a) => !a.startsWith('--')) || __dirname);
const PARA = { gerentes: 'Para gerentes', tecnicos: 'Para técnicos', todos: 'Para todos' };
const NIVEL = {
  Estable: 'ok', Verificado: 'ok',
  Vigilar: 'warn', Parcial: 'warn',
  Reentrenar: 'bad', Pendiente: 'bad',
};
const PSI_DEMO = [
  ['ingreso · edad', 0.002], ['canal', 0.360], ['(predicción)', 0.509], ['atraso', 0.867],
];

// ── marcas de texto: **negrita**, *cursiva*, `código` ──────────────────────
function tokens(texto) {
  return String(texto).split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/).filter(Boolean).map((p) => {
    if (p.startsWith('**')) return { x: p.slice(2, -2), b: true };
    if (p.startsWith('`')) return { x: p.slice(1, -1), code: true };
    if (p.startsWith('*') && p.endsWith('*') && p.length > 2) return { x: p.slice(1, -1), i: true };
    return { x: p };
  });
}

// ════════════════════════════════════════════════════════════════ HTML ════
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

function inl(texto) {
  return tokens(texto).map((t) => {
    if (t.b) return `<strong>${esc(t.x)}</strong>`;
    if (t.i) return `<em>${esc(t.x)}</em>`;
    if (t.code) return `<code>${esc(t.x)}</code>`;
    return esc(t.x);
  }).join('');
}

function chip(texto) {
  const plano = texto.replace(/\*/g, '');
  const k = NIVEL[plano];
  return k ? `<span class="chip chip-${k}">${esc(plano)}</span>` : inl(texto);
}

function tablaHtml(b) {
  const marcadas = new Set([b.semaforo, b.estado].filter((v) => v !== undefined));
  const num = (i) => b.semaforo !== undefined && i > 0 && i < b.semaforo;
  const cols = b.ancho.map((w) => `<col style="width:${w}%">`).join('');
  const head = b.head.map((h, i) => `<th class="${num(i) ? 'n' : ''}">${esc(h)}</th>`).join('');
  const filas = b.filas.map((f) => `<tr>${f.map((c, i) => `<td class="${num(i) ? 'n' : ''}">${
    marcadas.has(i) ? chip(c) : inl(c)}</td>`).join('')}</tr>`).join('');
  return `<div class="tabla"><table><colgroup>${cols}</colgroup><thead><tr>${head}</tr></thead>`
    + `<tbody>${filas}</tbody></table></div>`;
}

const VENTANAS_HTML = `<figure class="ventanas" aria-label="Las tres ventanas de validación">
  <div class="v v-tr"><b>Entrenamiento</b><span>ajusta · 60 %</span></div>
  <div class="v v-se"><b>Selección</b><span>elige · 20 %</span></div>
  <div class="v v-ho"><b>Holdout ciego</b><span>reporta · 20 %</span></div>
  <figcaption>El número que se informa sale de la tercera ventana, que no participó de ninguna decisión.
  Proporciones de la demo de esta guía: 2.399 · 800 · 801 filas.</figcaption>
</figure>`;

const PSI_HTML = `<div class="psi-tabla">
  <div class="z z-ok"><span class="mono">PSI &lt; 0,10</span><b>Estable</b><small>Misma población</small></div>
  <div class="z z-warn"><span class="mono">0,10 a 0,25</span><b>Vigilar</b><small>Se movió algo</small></div>
  <div class="z z-bad"><span class="mono">0,25 o más</span><b>Reentrenar</b><small>Cambió la población</small></div>
</div>`;

function psiDemoHtml() {
  const x = (v) => `${(Math.min(v, 1) * 100).toFixed(1)}%`;
  const marcas = PSI_DEMO.map(([n, v], i) => `<div class="m m${i} ${i % 2 ? 'abajo' : ''}" style="left:${x(v)}">`
    + `<i></i><span><b>${esc(n)}</b> ${v.toFixed(3).replace('.', ',')}</span></div>`).join('');
  return `<figure class="escala" aria-label="PSI de septiembre sobre la escala">
  <div class="barra"><span class="zb zb-ok" style="width:10%"></span><span class="zb zb-warn" style="width:15%"></span><span class="zb zb-bad" style="width:75%"></span>${marcas}</div>
  <div class="ejes"><span style="left:0">0</span><span style="left:10%">0,10</span><span style="left:25%">0,25</span><span style="left:50%">0,50</span><span style="left:100%">1,00</span></div>
  <figcaption>Septiembre sobre la escala del PSI: lo que se cambió cae en rojo; lo que no, pegado al cero.</figcaption>
</figure>`;
}

function bloqueHtml(b) {
  switch (b.t) {
    case 'lead': return `<p class="lead">${inl(b.x)}</p>`;
    case 'p': return `<p>${inl(b.x)}</p>`;
    case 'h3': return `<h3>${inl(b.x)}</h3>`;
    case 'ul': return `<ul>${b.items.map((i) => `<li>${inl(i)}</li>`).join('')}</ul>`;
    case 'steps': return `<ol class="pasos">${b.items.map(([t, x]) =>
      `<li><div><h4>${inl(t)}</h4><p>${inl(x)}</p></div></li>`).join('')}</ol>`;
    case 'table': return tablaHtml(b);
    case 'code': return `<pre class="codigo"><code>${esc(b.x)}</code></pre>`;
    case 'callout': return `<aside class="aviso aviso-${b.tipo}"><h4>${inl(b.titulo)}</h4><p>${inl(b.x)}</p></aside>`;
    case 'qa': return `<dl class="qa">${b.items.map(([q, a]) => `<div><dt>${inl(q)}</dt><dd>${inl(a)}</dd></div>`).join('')}</dl>`;
    case 'ventanas': return VENTANAS_HTML;
    case 'psi': return PSI_HTML;
    default: throw new Error(`Bloque desconocido: ${b.t}`);
  }
}

function seccionHtml(s, i) {
  let cuerpo = s.bloques.map(bloqueHtml).join('\n');
  if (s.id === 'deriva') cuerpo = cuerpo.replace('</table></div>', `</table></div>${psiDemoHtml()}`);
  return `<section id="${s.id}" data-para="${s.para}">
  <header class="sec-head"><span class="sec-num">${String(i + 1).padStart(2, '0')}</span>
  <h2>${inl(s.titulo)}</h2><span class="para para-${s.para}">${PARA[s.para]}</span></header>
  ${cuerpo}
</section>`;
}

const CSS = `
:root{
  --navy:#081527; --navy2:#0f2340; --amber:#f2b441; --amber-ink:#5c3d00; --blue:#215ea3;
  --paper:#ffffff; --ground:#f4f7fb; --ink:#122238; --muted:#586a80; --line:#e1e8f1; --soft:#eef3f9;
  --ok:#0a7d5a; --ok-bg:#e3f5ee; --warn:#9a6200; --warn-bg:#fdf1d8; --bad:#b3261e; --bad-bg:#fbe6e4;
  --code-bg:#0c1d33; --code-ink:#dfe9f6;
  --display:"Archivo","Segoe UI",system-ui,sans-serif;
  --body:"Source Sans 3","Segoe UI",system-ui,-apple-system,sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    color-scheme:dark;
    --paper:#0e1d33; --ground:#081527; --ink:#e6eef9; --muted:#9db0c8; --line:#1f3654; --soft:#132844;
    --blue:#7fb2ec; --amber-ink:#f2b441;
    --ok:#4fd1a5; --ok-bg:#0f3a30; --warn:#f2c265; --warn-bg:#3d2f10; --bad:#ff8a80; --bad-bg:#43191a;
    --code-bg:#050e1b;
  }
}
:root[data-theme="dark"]{
  color-scheme:dark;
  --paper:#0e1d33; --ground:#081527; --ink:#e6eef9; --muted:#9db0c8; --line:#1f3654; --soft:#132844;
  --blue:#7fb2ec; --amber-ink:#f2b441;
  --ok:#4fd1a5; --ok-bg:#0f3a30; --warn:#f2c265; --warn-bg:#3d2f10; --bad:#ff8a80; --bad-bg:#43191a;
  --code-bg:#050e1b;
}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font:17px/1.6 var(--body)}
a{color:var(--blue)}
code{font-family:var(--mono);font-size:.86em;background:var(--soft);padding:.08em .35em;border-radius:4px}
.portada{background:var(--navy);color:#eaf1fb;padding-block:56px 40px;padding-inline:16px;border-bottom:4px solid var(--amber)}
.portada .in{max-width:1120px;margin:0 auto}
.marca{font:600 13px/1 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--amber)}
.portada h1{font:800 clamp(38px,6vw,64px)/1.02 var(--display);margin:14px 0 14px;letter-spacing:-.02em;text-wrap:balance}
.portada .bajada{font-size:clamp(18px,2.2vw,21px);max-width:44em;color:#c9d6e8;margin:0}
.portada .meta{margin-top:18px;font:14px var(--mono);color:#9db0c8}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:34px}
.kpi{border-top:1px solid #2a4160;padding-top:12px}
.kpi b{display:block;font:800 40px/1 var(--display);color:var(--amber);font-variant-numeric:tabular-nums}
.kpi span{display:block;margin-top:6px;font-size:14px;color:#b7c6da;line-height:1.35}
.filtro{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--paper);border-bottom:1px solid var(--line)}
.filtro .in{max-width:1120px;margin:0 auto;padding:10px 16px;display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.filtro .lbl{font:600 12px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-right:4px}
.filtro button{font:600 14px var(--body);color:var(--ink);background:transparent;border:1px solid var(--line);border-radius:999px;padding:6px 14px;cursor:pointer}
.filtro button[aria-pressed="true"]{background:var(--navy);border-color:var(--navy);color:#fff}
:root[data-theme="dark"] .filtro button[aria-pressed="true"]{background:var(--amber);border-color:var(--amber);color:#1c1305}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]) .filtro button[aria-pressed="true"]{background:var(--amber);border-color:var(--amber);color:#1c1305}}
.filtro button:focus-visible,.indice a:focus-visible{outline:2px solid var(--amber);outline-offset:2px}
.cuerpo{max-width:1120px;margin:0 auto;padding-inline:16px;padding-block:32px 64px;display:grid;grid-template-columns:220px minmax(0,1fr);gap:48px}
.indice{position:sticky;top:72px;align-self:start;font-size:14px}
.indice ol{list-style:none;margin:0;padding:0;display:grid;gap:2px}
.indice a{display:flex;gap:10px;text-decoration:none;color:var(--muted);padding:5px 8px;border-radius:6px;line-height:1.3}
.indice a:hover{background:var(--soft);color:var(--ink)}
.indice a span{font:12px var(--mono);color:var(--amber-ink);padding-top:2px}
main{min-width:0;display:grid;grid-template-columns:minmax(0,1fr);gap:22px}
section{background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:28px clamp(18px,3.5vw,40px) 30px}
section[hidden]{display:none!important}
.sec-head{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 14px;margin-bottom:10px}
.sec-num{font:600 14px var(--mono);color:var(--amber-ink)}
h2{font:800 clamp(24px,3vw,30px)/1.15 var(--display);margin:0;letter-spacing:-.01em;text-wrap:balance;flex:1 1 16em}
h3{font:700 19px/1.3 var(--display);margin:26px 0 8px}
h4{font:700 16px/1.3 var(--display);margin:0 0 4px}
p{margin:10px 0;max-width:68ch}
.lead{font-size:19px;line-height:1.55;max-width:62ch}
.para{font:600 11px var(--mono);letter-spacing:.1em;text-transform:uppercase;padding:4px 9px;border-radius:999px;background:var(--soft);color:var(--muted)}
.para-gerentes{background:var(--warn-bg);color:var(--warn)}
.para-tecnicos{background:var(--soft);color:var(--blue)}
ul{padding-left:1.2em;margin:10px 0;max-width:72ch}
li{margin:6px 0}
li::marker{color:var(--amber-ink)}
.pasos{list-style:none;counter-reset:p;padding:0;margin:14px 0;display:grid;gap:0}
.pasos li{counter-increment:p;display:grid;grid-template-columns:44px 1fr;gap:14px;margin:0;padding:12px 0;border-top:1px solid var(--line)}
.pasos li:first-child{border-top:0}
.pasos li::before{content:counter(p,decimal-leading-zero);font:700 15px/1.4 var(--mono);color:var(--amber-ink);padding-top:1px}
.pasos p{margin:0}
.tabla{overflow-x:auto;margin:14px 0;border:1px solid var(--line);border-radius:8px}
table{width:100%;border-collapse:collapse;font-size:15px;min-width:560px}
th{font:600 12px var(--mono);letter-spacing:.06em;text-transform:uppercase;text-align:left;color:var(--muted);background:var(--soft);padding:10px 12px}
td{padding:11px 12px;border-top:1px solid var(--line);vertical-align:top;line-height:1.45}
td.n,th.n{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums}
.chip{display:inline-block;font:600 13px var(--body);padding:2px 10px;border-radius:999px;white-space:nowrap}
.chip-ok{background:var(--ok-bg);color:var(--ok)} .chip-warn{background:var(--warn-bg);color:var(--warn)} .chip-bad{background:var(--bad-bg);color:var(--bad)}
.codigo{background:var(--code-bg);color:var(--code-ink);border-radius:8px;padding:16px 18px;overflow-x:auto;font:14px/1.6 var(--mono);margin:14px 0}
.codigo code{background:none;padding:0;font-size:inherit;color:inherit}
.aviso{border-radius:8px;padding:14px 18px;margin:16px 0;border:1px solid}
.aviso p{margin:4px 0 0}
.aviso-warn{background:var(--warn-bg);border-color:color-mix(in srgb,var(--warn) 35%,transparent)}
.aviso-info{background:var(--soft);border-color:var(--line)}
.ventanas{margin:14px 0 6px;display:grid;grid-template-columns:3fr 1fr 1fr;gap:4px}
.ventanas .v{padding:14px 14px;border-radius:6px;display:grid;gap:2px;min-width:0}
.ventanas b{font:700 15px var(--display)} .ventanas span{font:13px var(--mono)}
.v-tr{background:var(--soft);color:var(--ink)} .v-se{background:color-mix(in srgb,var(--blue) 18%,var(--paper));color:var(--ink)}
.v-ho{background:var(--navy);color:#fff;box-shadow:inset 0 -4px 0 var(--amber)}
.ventanas figcaption,.escala figcaption{grid-column:1/-1;font-size:14px;color:var(--muted);margin-top:6px}
.psi-tabla{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:16px 0}
.z{border-radius:8px;padding:12px 14px;display:grid;gap:2px}
.z .mono{font:600 13px var(--mono)} .z b{font:800 20px var(--display)} .z small{font-size:13px;opacity:.85}
.z-ok{background:var(--ok-bg);color:var(--ok)} .z-warn{background:var(--warn-bg);color:var(--warn)} .z-bad{background:var(--bad-bg);color:var(--bad)}
.escala{margin:24px 0 8px;padding:0 8px}
.barra{position:relative;height:14px;display:flex;border-radius:7px;margin:44px 0 44px}
.zb{height:100%} .zb-ok{background:var(--ok);border-radius:7px 0 0 7px} .zb-warn{background:#e0a030} .zb-bad{background:var(--bad);border-radius:0 7px 7px 0}
.m{position:absolute;top:-6px;transform:translateX(-50%)}
.m i{display:block;width:4px;height:26px;background:var(--ink);border-radius:2px;margin:0 auto}
.m span{position:absolute;bottom:30px;left:50%;transform:translateX(-50%);white-space:nowrap;font:12px var(--mono);color:var(--ink)}
.m.abajo span{bottom:auto;top:30px}
.m:first-of-type span{left:0;transform:none}
.m:last-of-type span{left:auto;right:0;transform:none}
.ejes{position:relative;height:18px;font:12px var(--mono);color:var(--muted)}
.ejes span{position:absolute;transform:translateX(-50%)}
.ejes span:first-child{transform:none} .ejes span:last-child{transform:translateX(-100%)}
.qa{margin:8px 0;display:grid;gap:0}
.qa div{padding:14px 0;border-top:1px solid var(--line)} .qa div:first-child{border-top:0}
.qa dt{font:700 17px/1.35 var(--display)} .qa dd{margin:4px 0 0;max-width:68ch}
.cierre{font:600 clamp(19px,2.2vw,22px)/1.45 var(--display);max-width:44em;margin:8px 0 0;padding:26px 30px;border-radius:10px;background:var(--navy);color:#eaf1fb;border-left:4px solid var(--amber)}
.pie{max-width:1120px;margin:0 auto;padding:0 16px 40px;font:13px var(--mono);color:var(--muted)}
@media (max-width:900px){
  .cuerpo{grid-template-columns:minmax(0,1fr);gap:18px}
  .indice{position:static}
  .indice ol{grid-template-columns:repeat(auto-fill,minmax(220px,1fr))}
  .kpis{grid-template-columns:repeat(2,1fr)}
}
@media (max-width:560px){
  body{font-size:16px}
  .psi-tabla{grid-template-columns:1fr}
  .ventanas{grid-template-columns:1fr}
  .m span{font-size:11px}
  .barra{margin-top:62px}
  .m.m2 span{bottom:48px}
}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
@media print{.filtro,.indice{display:none}.cuerpo{display:block}section{break-inside:avoid-page;border:0}}
`;

const JS = `
(function(){
  var botones = document.querySelectorAll('.filtro button');
  function aplicar(v){
    botones.forEach(function(b){ b.setAttribute('aria-pressed', String(b.dataset.v === v)); });
    document.querySelectorAll('section[data-para]').forEach(function(s){
      var p = s.dataset.para;
      s.hidden = !(v === 'todo' || p === 'todos' || p === v);
      var enlace = document.querySelector('.indice a[href="#' + s.id + '"]');
      if (enlace) enlace.parentElement.hidden = s.hidden;
    });
    try { localStorage.setItem('mv-guia-publico', v); } catch (e) { /* sin almacenamiento: no pasa nada */ }
  }
  botones.forEach(function(b){ b.addEventListener('click', function(){ aplicar(b.dataset.v); }); });
  var guardado = 'todo';
  try { guardado = localStorage.getItem('mv-guia-publico') || 'todo'; } catch (e) { guardado = 'todo'; }
  aplicar(guardado);
})();
`;

function cuerpoHtml() {
  const indice = SECCIONES.map((s, i) => `<li><a href="#${s.id}"><span>${String(i + 1).padStart(2, '0')}</span>${esc(s.titulo)}</a></li>`).join('');
  return `<title>${esc(META.titulo)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;700;800&family=IBM+Plex+Mono:wght@400;600&family=Source+Sans+3:ital,wght@0,400;0,600;0,700;1,400&display=swap">
<style>${CSS}</style>
<header class="portada"><div class="in">
  <div class="marca">Guía para gerentes y técnicos</div>
  <h1>${esc(META.titulo)}</h1>
  <p class="bajada">${inl(META.bajada)}</p>
  <div class="meta">${esc(META.version)} · ${esc(META.autor)}</div>
  <div class="kpis">${KPIS.map(([n, l]) => `<div class="kpi"><b>${esc(n)}</b><span>${esc(l)}</span></div>`).join('')}</div>
</div></header>
<nav class="filtro" aria-label="Filtrar por público"><div class="in">
  <span class="lbl">Leer como</span>
  <button type="button" id="ver-todo" data-v="todo" aria-pressed="true">Todo</button>
  <button type="button" id="ver-gerentes" data-v="gerentes" aria-pressed="false">Gerente</button>
  <button type="button" id="ver-tecnicos" data-v="tecnicos" aria-pressed="false">Técnico</button>
</div></nav>
<div class="cuerpo">
  <nav class="indice" aria-label="Índice"><ol>${indice}</ol></nav>
  <main>
${SECCIONES.map(seccionHtml).join('\n')}
<p class="cierre">${inl(CIERRE)}</p>
  </main>
</div>
<footer class="pie">${esc(META.producto)} · ${esc(META.version)} · generado desde docs/presentacion/contenido.js</footer>
<script>${JS}</script>
`;
}

function documentoHtml(cuerpo) {
  const corte = cuerpo.indexOf('<header class="portada">');
  return '<!doctype html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n'
    + '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
    + `${cuerpo.slice(0, corte)}</head>\n<body>\n${cuerpo.slice(corte)}</body>\n</html>\n`;
}

// ════════════════════════════════════════════════════════════════ DOCX ════
function docxDoc() {
  const D = require('docx');
  const {
    AlignmentType, BorderStyle, Document, Footer, HeadingLevel, LevelFormat, Packer, PageNumber,
    Paragraph, ShadingType, Table, TableCell, TableRow, TextRun, WidthType,
  } = D;
  const ANCHO = 11906 - 2 * 1134;                 // A4 con márgenes de 2 cm
  const C = { navy: '081527', amber: 'F2B441', ink: '122238', muted: '586A80', line: 'D5DEE9',
    soft: 'EEF3F9', ok: '0A7D5A', okbg: 'E3F5EE', warn: '9A6200', warnbg: 'FDF1D8', bad: 'B3261E', badbg: 'FBE6E4' };
  const TONO = { ok: [C.ok, C.okbg], warn: [C.warn, C.warnbg], bad: [C.bad, C.badbg] };
  let pasos = 0;

  const runs = (texto, extra = {}) => tokens(texto).map((t) => new TextRun({
    text: t.x, bold: t.b || extra.bold, italics: t.i, color: extra.color,
    font: t.code ? 'Consolas' : undefined, size: extra.size,
  }));
  const par = (texto, o = {}) => new Paragraph({ children: runs(texto, o), spacing: { after: 120 }, ...o.p });
  const borde = { style: BorderStyle.SINGLE, size: 4, color: C.line };
  const bordes = { top: borde, bottom: borde, left: borde, right: borde };

  function celda(contenido, ancho, o = {}) {
    return new TableCell({
      width: { size: ancho, type: WidthType.DXA }, borders: bordes,
      shading: o.fondo ? { type: ShadingType.CLEAR, fill: o.fondo, color: 'auto' } : undefined,
      margins: { top: 90, bottom: 90, left: 110, right: 110 },
      children: [new Paragraph({ alignment: o.derecha ? AlignmentType.RIGHT : AlignmentType.LEFT,
        children: runs(contenido, { bold: o.bold, color: o.color, size: o.size || 19 }) })],
    });
  }

  function tabla(b) {
    const anchos = b.ancho.map((w) => Math.round(ANCHO * w / 100));
    anchos[anchos.length - 1] += ANCHO - anchos.reduce((a, c) => a + c, 0);
    const marcadas = new Set([b.semaforo, b.estado].filter((v) => v !== undefined));
    const num = (i) => b.semaforo !== undefined && i > 0 && i < b.semaforo;
    const cab = new TableRow({ tableHeader: true, children: b.head.map((h, i) =>
      celda(h, anchos[i], { fondo: C.navy, color: 'FFFFFF', bold: true, size: 18, derecha: num(i) })) });
    const filas = b.filas.map((f) => new TableRow({ children: f.map((c, i) => {
      const k = marcadas.has(i) && NIVEL[c.replace(/\*/g, '')];
      return k ? celda(c, anchos[i], { fondo: TONO[k][1], color: TONO[k][0], bold: true })
        : celda(c, anchos[i], { derecha: num(i) });
    }) }));
    return [new Table({ width: { size: ANCHO, type: WidthType.DXA }, columnWidths: anchos, rows: [cab, ...filas] }),
      new Paragraph({ spacing: { after: 120 }, children: [] })];
  }

  function franjas(celdas) {
    const anchos = celdas.map(([w]) => Math.round(ANCHO * w / 100));
    anchos[anchos.length - 1] += ANCHO - anchos.reduce((a, c) => a + c, 0);
    const fila = new TableRow({ children: celdas.map(([, fondo, color, titulo, sub], i) => new TableCell({
      width: { size: anchos[i], type: WidthType.DXA }, borders: bordes,
      shading: { type: ShadingType.CLEAR, fill: fondo, color: 'auto' },
      margins: { top: 120, bottom: 120, left: 140, right: 140 },
      children: [new Paragraph({ children: [new TextRun({ text: titulo, bold: true, color, size: 22 })] }),
        new Paragraph({ children: [new TextRun({ text: sub, color, size: 18, font: 'Consolas' })] })],
    })) });
    return [new Table({ width: { size: ANCHO, type: WidthType.DXA }, columnWidths: anchos, rows: [fila] }),
      new Paragraph({ spacing: { after: 160 }, children: [] })];
  }

  function bloque(b) {
    switch (b.t) {
      case 'lead': return [par(b.x, { size: 24 })];
      case 'p': return [par(b.x)];
      case 'h3': return [new Paragraph({ heading: HeadingLevel.HEADING_3, children: runs(b.x) })];
      case 'ul': return b.items.map((i) => new Paragraph({ numbering: { reference: 'vinetas', level: 0 },
        spacing: { after: 80 }, children: runs(i) }));
      case 'steps': {
        pasos += 1;
        return b.items.map(([t, x]) => new Paragraph({
          numbering: { reference: 'pasos', level: 0, instance: pasos }, spacing: { after: 100 },
          children: [...runs(t, { bold: true }), new TextRun({ text: '. ' }), ...runs(x)] }));
      }
      case 'table': return tabla(b);
      case 'code': return b.x.split('\n').map((l, i, arr) => new Paragraph({
        shading: { type: ShadingType.CLEAR, fill: C.soft, color: 'auto' },
        spacing: { after: i === arr.length - 1 ? 160 : 0 },
        children: [new TextRun({ text: l || ' ', font: 'Consolas', size: 18 })] }));
      case 'callout': {
        const [color, fondo] = b.tipo === 'warn' ? [C.warn, C.warnbg] : [C.navy, C.soft];
        return [new Table({ width: { size: ANCHO, type: WidthType.DXA }, columnWidths: [ANCHO], rows: [
          new TableRow({ children: [new TableCell({ width: { size: ANCHO, type: WidthType.DXA },
            borders: { ...bordes, left: { style: BorderStyle.SINGLE, size: 24, color } },
            shading: { type: ShadingType.CLEAR, fill: fondo, color: 'auto' },
            margins: { top: 120, bottom: 120, left: 180, right: 180 },
            children: [new Paragraph({ spacing: { after: 60 }, children: runs(b.titulo, { bold: true, color }) }),
              new Paragraph({ children: runs(b.x, { size: 20 }) })] })] })] }),
        new Paragraph({ spacing: { after: 120 }, children: [] })];
      }
      case 'qa': return b.items.flatMap(([q, a]) => [
        new Paragraph({ keepNext: true, spacing: { before: 120, after: 40 }, children: runs(q, { bold: true, color: C.navy }) }),
        par(a)]);
      case 'ventanas': return franjas([
        [60, C.soft, C.ink, 'Entrenamiento', 'ajusta · 60 %'],
        [20, 'D6E3F3', C.ink, 'Selección', 'elige · 20 %'],
        [20, C.navy, 'FFFFFF', 'Holdout ciego', 'reporta · 20 %']]);
      case 'psi': return franjas([
        [33, C.okbg, C.ok, 'Estable', 'PSI < 0,10'],
        [33, C.warnbg, C.warn, 'Vigilar', '0,10 a 0,25'],
        [34, C.badbg, C.bad, 'Reentrenar', '0,25 o más']]);
      default: throw new Error(`Bloque desconocido: ${b.t}`);
    }
  }

  const portada = [
    new Paragraph({ spacing: { before: 1800, after: 200 }, children: [new TextRun({
      text: 'GUÍA PARA GERENTES Y TÉCNICOS', color: 'B07A12', bold: true, size: 20, characterSpacing: 40 })] }),
    new Paragraph({ spacing: { after: 240 }, children: [new TextRun({ text: META.titulo, bold: true, size: 72, color: C.navy })] }),
    new Paragraph({ spacing: { after: 360 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 18, color: C.amber, space: 12 } },
      children: runs(META.bajada, { size: 28, color: C.ink }) }),
    par(`${META.version} · ${META.autor}`, { color: C.muted }),
    new Paragraph({ spacing: { before: 600 }, children: [] }),
    ...(() => {
      const a = Math.round(ANCHO / 4);
      const anchos = [a, a, a, ANCHO - 3 * a];
      return [new Table({ width: { size: ANCHO, type: WidthType.DXA }, columnWidths: anchos, rows: [
        new TableRow({ children: KPIS.map(([n, l], i) => new TableCell({
          width: { size: anchos[i], type: WidthType.DXA },
          borders: { top: { style: BorderStyle.SINGLE, size: 12, color: C.amber }, bottom: { style: BorderStyle.NONE, size: 0, color: 'auto' },
            left: { style: BorderStyle.NONE, size: 0, color: 'auto' }, right: { style: BorderStyle.NONE, size: 0, color: 'auto' } },
          margins: { top: 120, bottom: 60, left: 60, right: 160 },
          children: [new Paragraph({ children: [new TextRun({ text: n, bold: true, size: 56, color: C.navy })] }),
            new Paragraph({ children: [new TextRun({ text: l, size: 18, color: C.muted })] })] })) })] })];
    })(),
  ];

  const cuerpo = SECCIONES.flatMap((s, i) => [
    new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: i === 0, spacing: { before: i === 0 ? 0 : 520, after: 80 },
      children: [new TextRun({ text: `${String(i + 1).padStart(2, '0')}  `, color: 'B07A12' }), ...runs(s.titulo)] }),
    new Paragraph({ spacing: { after: 200 }, children: [new TextRun({ text: PARA[s.para].toUpperCase(),
      size: 16, bold: true, color: C.muted, characterSpacing: 30 })] }),
    ...s.bloques.flatMap(bloque),
  ]);

  const cierre = [new Paragraph({ spacing: { before: 360 },
    border: { left: { style: BorderStyle.SINGLE, size: 24, color: C.amber, space: 12 } },
    indent: { left: 240 }, children: runs(CIERRE, { size: 26, bold: true, color: C.navy }) })];

  const doc = new Document({
    creator: META.autor, title: META.titulo, description: META.bajada,
    styles: {
      default: { document: { run: { font: 'Calibri', size: 21, color: C.ink } } },
      paragraphStyles: [
        { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { size: 40, bold: true, color: C.navy }, paragraph: { spacing: { before: 0, after: 80 }, outlineLevel: 0 } },
        { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { size: 26, bold: true, color: C.navy }, paragraph: { spacing: { before: 280, after: 100 }, outlineLevel: 2, keepNext: true } },
      ],
    },
    numbering: { config: [
      { reference: 'vinetas', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 440, hanging: 280 } }, run: { color: 'B07A12' } } }] },
      { reference: 'pasos', levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 440, hanging: 360 } }, run: { bold: true, color: 'B07A12' } } }] },
    ] },
    sections: [{
      properties: { page: { size: { width: 11906, height: 16838 },
        margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } },
      footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [
        new TextRun({ text: `${META.producto} · página `, size: 16, color: C.muted }),
        new TextRun({ children: [PageNumber.CURRENT], size: 16, color: C.muted })] })] }) },
      children: [...portada, ...cuerpo, ...cierre],
    }],
  });
  return Packer.toBuffer(doc);
}

// ═══════════════════════════════════════════════════════════════ salida ════
async function main() {
  fs.mkdirSync(SALIDA, { recursive: true });
  const cuerpo = cuerpoHtml();
  const html = path.join(SALIDA, `${META.archivo}.html`);
  fs.writeFileSync(html, documentoHtml(cuerpo));
  if (ARGS.includes('--pagina')) fs.writeFileSync(path.join(SALIDA, `${META.archivo}.cuerpo.html`), cuerpo);
  const docx = path.join(SALIDA, `${META.archivo}.docx`);
  fs.writeFileSync(docx, await docxDoc());
  console.log(`HTML: ${html}\nWord: ${docx}`);
}

main().catch((err) => { console.error(err); process.exit(1); });
