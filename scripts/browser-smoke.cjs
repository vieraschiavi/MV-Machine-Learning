/**
 * Prueba de humo en navegador real.
 *
 * No corre en CI a propósito: depende de un navegador y de un servidor
 * levantado, y una prueba que depende del entorno vuelve rojo el pipeline por
 * motivos que no son del código. Se corre a mano antes de una entrega:
 *
 *   pip install -r requirements.txt && ./scripts/run.sh     (en otra terminal)
 *   npm install playwright && node scripts/browser-smoke.cjs
 */
const { chromium } = require('playwright');

const BASE = process.env.MV_URL || 'http://127.0.0.1:8000';
const VISTAS = ['overview', 'data', 'explore', 'etl', 'model', 'results', 'ai', 'export'];
const IDIOMAS = ['es', 'en', 'pt'];

(async () => {
  const errores = [];
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined,
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  page.on('console', (m) => { if (m.type() === 'error') errores.push(`consola: ${m.text()}`); });
  page.on('pageerror', (e) => errores.push(`excepción: ${e.message}`));

  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);

  for (const lang of IDIOMAS) {
    await page.selectOption('#lang-select', lang);
    await page.waitForTimeout(400);
    const nav = await page.$$eval('.nav-item', (e) => e.map((x) => x.textContent.trim()));
    if (nav.length !== VISTAS.length) errores.push(`${lang}: la navegación tiene ${nav.length} entradas`);
    console.log(`idioma ${lang}: ${nav.join(' · ')}`);
  }

  for (const vista of VISTAS) {
    await page.click(`.nav-item[data-view="${vista}"]`);
    await page.waitForTimeout(800);
    const titulo = await page.textContent(`#view-${vista} h1`).catch(() => null);
    if (!titulo) errores.push(`la vista ${vista} no renderizó su título`);
    console.log(`vista ${vista}: ${titulo}`);
  }

  await page.click('#theme-btn');
  await page.waitForTimeout(300);
  const tema = await page.getAttribute('html', 'data-theme');
  console.log(`tema: ${tema}`);

  await browser.close();
  console.log(`\nerrores: ${errores.length}`);
  errores.forEach((e) => console.log(`  ${e}`));
  process.exit(errores.length ? 1 : 0);
})();
