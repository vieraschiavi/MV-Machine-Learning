#!/usr/bin/env python3
"""
cicd_check.py — Gate del módulo 18 (CI/CD) del skill all-in-one-tech-team.

Audita workflows de GitHub Actions buscando los antipatrones que actionlint NO marca
(actionlint valida sintaxis y tipos; este script valida seguridad y política del pipeline):

  BLOQUEANTE  secretos en texto plano, tests con continue-on-error, pull_request_target que
              hace checkout del código del PR, deploy que corre desde un pull_request
  MAYOR       permissions write-all o ausentes, actions sin versión fija (@main/@master/sin ref),
              inyección de ${{ github.event.* }} en run, deploy sin gate de CI, CI sin tests
  MENOR       sin concurrency

Si actionlint está en el PATH, también lo corre y suma sus errores como BLOQUEANTE.

Uso:
  python cicd_check.py                     # audita .github/workflows del directorio actual
  python cicd_check.py ruta/a/workflows    # carpeta o archivo .yml puntual
  python cicd_check.py --demo              # autotest: 1 workflow sano (debe pasar) y 1 roto (debe fallar)
  python cicd_check.py ruta --json         # salida JSON

Exit code: 0 = sin hallazgos BLOQUEANTE/MAYOR · 1 = hay hallazgos · 2 = error de uso.
Requiere: Python 3.8+ y PyYAML (pip install pyyaml).
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("ERROR: falta PyYAML. Instalar con: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

SEVERIDADES = ("BLOQUEANTE", "MAYOR", "MENOR")

PATRONES_SECRETO = [
    (r"ghp_[A-Za-z0-9]{36}", "token personal de GitHub"),
    (r"github_pat_[A-Za-z0-9_]{22,}", "token fine-grained de GitHub"),
    (r"AKIA[0-9A-Z]{16}", "access key de AWS"),
    (r"xox[baprs]-[A-Za-z0-9-]{10,}", "token de Slack"),
    (r"sk-[A-Za-z0-9_-]{20,}", "API key tipo sk-"),
    (r"(?i)(password|passwd|token|api[_-]?key|secret)\s*[:=]\s*['\"]?(?!\$\{\{)[A-Za-z0-9/+_\-]{8,}", "credencial literal"),
]
PATRON_TEST = re.compile(
    r"\b(pytest|unittest|npm (run )?test|yarn test|pnpm test|jest|vitest|playwright test|"
    r"go test|cargo test|mvn test|gradle test|testthat|test_dir|test_check|rcmdcheck|dotnet test)\b"
)
PATRON_DEPLOY = re.compile(
    r"\b(vercel deploy|netlify deploy|kubectl apply|helm (upgrade|install)|terraform apply|"
    r"aws (s3 sync|ecs update-service|lambda update-function-code)|gcloud (run deploy|app deploy)|"
    r"firebase deploy|fly deploy|docker push|az webapp deploy)\b"
)
ACCIONES_DEPLOY = ("docker/build-push-action", "amondnet/vercel-action", "azure/webapps-deploy",
                   "google-github-actions/deploy")
PATRON_INYECCION = re.compile(
    r"\$\{\{\s*github\.(event\.(pull_request\.(title|body|head\.ref)|issue\.(title|body)|"
    r"comment\.body|review\.body|head_commit\.message)|head_ref)\s*\}\}"
)


def _triggers(doc):
    on = doc.get("on", doc.get(True))  # PyYAML convierte la clave `on` en True
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {t: None for t in on}
    return on or {}


def _steps(job):
    return job.get("steps") or []


def _texto_job(job):
    partes = []
    for st in _steps(job):
        partes.append(str(st.get("run", "")))
        partes.append(str(st.get("uses", "")))
        partes.append(str(st.get("name", "")))
    return "\n".join(partes)


def _es_deploy(job):
    texto = _texto_job(job)
    if PATRON_DEPLOY.search(texto):
        return True
    for st in _steps(job):
        uses = str(st.get("uses", ""))
        if uses.startswith(ACCIONES_DEPLOY):
            with_ = st.get("with") or {}
            if uses.startswith("docker/build-push-action") and str(with_.get("push", "")).lower() != "true":
                continue
            return True
    return False


def _linea(texto_crudo, aguja):
    for i, linea in enumerate(texto_crudo.splitlines(), 1):
        if aguja in linea:
            return i
    return None


def auditar_archivo(ruta):
    hallazgos = []
    crudo = Path(ruta).read_text(encoding="utf-8")

    def add(sev, regla, detalle, aguja=None):
        hallazgos.append({
            "archivo": str(ruta), "linea": _linea(crudo, aguja) if aguja else None,
            "severidad": sev, "regla": regla, "detalle": detalle,
        })

    # 1) Secretos en texto plano (sobre el texto crudo, antes de parsear)
    for i, linea in enumerate(crudo.splitlines(), 1):
        if linea.lstrip().startswith("#"):
            continue
        for patron, que in PATRONES_SECRETO:
            if re.search(patron, linea):
                hallazgos.append({"archivo": str(ruta), "linea": i, "severidad": "BLOQUEANTE",
                                  "regla": "secreto-en-texto-plano",
                                  "detalle": f"posible {que}; usar ${{{{ secrets.NOMBRE }}}}"})
                break

    try:
        doc = yaml.safe_load(crudo) or {}
    except yaml.YAMLError as e:
        add("BLOQUEANTE", "yaml-invalido", f"no parsea: {e}")
        return hallazgos
    if not isinstance(doc, dict) or "jobs" not in doc:
        add("BLOQUEANTE", "workflow-invalido", "no tiene la clave jobs")
        return hallazgos

    trig = _triggers(doc)
    jobs = doc.get("jobs") or {}

    # 2) Permisos
    perms = doc.get("permissions")
    if perms is None and not all("permissions" in (j or {}) for j in jobs.values()):
        add("MAYOR", "permissions-ausentes",
            "sin bloque permissions: el GITHUB_TOKEN hereda el default del repo; declarar el mínimo (contents: read)")
    if perms == "write-all" or any((j or {}).get("permissions") == "write-all" for j in jobs.values()):
        add("MAYOR", "permissions-write-all", "write-all da escritura total al token; declarar solo lo necesario",
            "write-all")

    # 3) Concurrency
    if "concurrency" not in doc and not any("concurrency" in (j or {}) for j in jobs.values()):
        add("MENOR", "sin-concurrency", "sin concurrency: dos pushes seguidos corren/deployan en paralelo")

    tiene_tests = False
    for nombre, job in jobs.items():
        job = job or {}
        # 4) Tests con continue-on-error
        job_coe = str(job.get("continue-on-error", "")).lower() == "true"
        for st in _steps(job):
            run = str(st.get("run", ""))
            uses = str(st.get("uses", ""))
            es_test = bool(PATRON_TEST.search(run) or PATRON_TEST.search(str(st.get("name", ""))))
            if es_test:
                tiene_tests = True
                if job_coe or str(st.get("continue-on-error", "")).lower() == "true":
                    add("BLOQUEANTE", "tests-no-bloquean",
                        f"job '{nombre}': continue-on-error en un paso de tests deja pasar código roto",
                        "continue-on-error")
            # 5) Actions sin versión fija
            if uses and not uses.startswith(("./", "docker://")):
                ref = uses.split("@", 1)[1] if "@" in uses else ""
                if ref in ("", "main", "master", "latest", "HEAD"):
                    add("MAYOR", "action-sin-version",
                        f"'{uses}' sin versión fija; usar tag (@v4) o SHA completo", uses)
            # 6) Inyección de expresiones no confiables en run
            m = PATRON_INYECCION.search(run)
            if m:
                add("MAYOR", "inyeccion-en-run",
                    f"job '{nombre}': {m.group(0)} dentro de run permite inyección; pasarlo por env:",
                    m.group(0))
            # 7) pull_request_target + checkout del PR
            if "pull_request_target" in trig and uses.startswith("actions/checkout"):
                ref_co = str((st.get("with") or {}).get("ref", ""))
                if "pull_request.head" in ref_co or "head_ref" in ref_co:
                    add("BLOQUEANTE", "prt-checkout-pr",
                        "pull_request_target + checkout del código del PR ejecuta código ajeno con secretos",
                        "pull_request_target")
        if "testthat" in _texto_job(job) or "check-r-package" in _texto_job(job):
            tiene_tests = True

        # 8) Deploy sin gate
        if _es_deploy(job):
            if "pull_request" in trig and not job.get("if"):
                add("BLOQUEANTE", "deploy-desde-pr",
                    f"job '{nombre}' deploya y el workflow corre en pull_request sin if: un PR publicaría")
            gateado = bool(job.get("needs")) or "workflow_run" in trig or bool(job.get("environment"))
            solo_tags = set(trig) == {"push"} and isinstance(trig.get("push"), dict) and \
                "tags" in trig["push"] and "branches" not in trig["push"]
            if not gateado and not solo_tags:
                add("MAYOR", "deploy-sin-gate",
                    f"job '{nombre}' deploya sin needs de CI, sin workflow_run y sin environment con aprobación")

    # 9) CI sin tests
    es_ci = "pull_request" in trig or "push" in trig
    hay_deploy = any(_es_deploy(j or {}) for j in jobs.values())
    if es_ci and not tiene_tests and not hay_deploy:
        add("MAYOR", "ci-sin-tests",
            "workflow de CI sin paso de tests: CI/CD automatiza las pruebas, no las reemplaza")
    return hallazgos


def correr_actionlint(archivos):
    binario = shutil.which("actionlint")
    if not binario:
        return None, []
    proc = subprocess.run([binario, "-color=false", *map(str, archivos)], capture_output=True, text=True)
    hallazgos = []
    for linea in proc.stdout.splitlines():
        m = re.match(r"^(.+?):(\d+):\d+: (.+?) \[(.+)\]$", linea)
        if m:
            hallazgos.append({"archivo": m.group(1), "linea": int(m.group(2)), "severidad": "BLOQUEANTE",
                              "regla": f"actionlint/{m.group(4)}", "detalle": m.group(3)})
    return proc.returncode, hallazgos


def listar_workflows(ruta):
    p = Path(ruta)
    if p.is_file():
        return [p]
    if p.is_dir():
        return sorted([*p.glob("*.yml"), *p.glob("*.yaml")])
    return []


def auditar(ruta, usar_actionlint=True):
    archivos = listar_workflows(ruta)
    if not archivos:
        raise FileNotFoundError(f"no se encontraron workflows .yml/.yaml en {ruta}")
    hallazgos = []
    for a in archivos:
        hallazgos.extend(auditar_archivo(a))
    estado_al = "omitido (--sin-actionlint / demo)"
    if usar_actionlint:
        estado_al = "no instalado (PARCIAL: correr actionlint localmente)"
        rc, h_al = correr_actionlint(archivos)
        if rc is not None:
            hallazgos.extend(h_al)
            estado_al = "OK" if rc == 0 else f"{len(h_al)} error(es)"
    return archivos, hallazgos, estado_al


def imprimir(archivos, hallazgos, estado_al):
    print(f"Workflows auditados: {len(archivos)}")
    for a in archivos:
        print(f"  - {a}")
    print(f"actionlint: {estado_al}")
    if not hallazgos:
        print("\nRESULTADO: VERDE — 0 hallazgos")
        return
    orden = {s: i for i, s in enumerate(SEVERIDADES)}
    print(f"\n{'SEVERIDAD':<11} {'REGLA':<24} UBICACIÓN / DETALLE")
    for h in sorted(hallazgos, key=lambda x: (orden[x["severidad"]], x["archivo"], x["linea"] or 0)):
        ubic = f"{Path(h['archivo']).name}:{h['linea']}" if h["linea"] else Path(h["archivo"]).name
        print(f"{h['severidad']:<11} {h['regla']:<24} {ubic} — {h['detalle']}")
    conteo = {s: sum(1 for h in hallazgos if h["severidad"] == s) for s in SEVERIDADES}
    bloquea = conteo["BLOQUEANTE"] + conteo["MAYOR"] > 0
    print(f"\nRESULTADO: {'ROJO' if bloquea else 'VERDE con observaciones'} — "
          f"BLOQUEANTE={conteo['BLOQUEANTE']} MAYOR={conteo['MAYOR']} MENOR={conteo['MENOR']}")


WF_SANO = """name: CI
on:
  push:
    branches: [main]
  pull_request:
permissions:
  contents: read
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install pytest
      - run: pytest
"""

WF_ROTO = """name: CI
on: [push, pull_request]
permissions: write-all
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@main
      - run: echo "${{ github.event.pull_request.title }}"
      - run: pytest
        continue-on-error: true
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: vercel deploy --prod --token={TOKEN_FALSO}
""".replace("{TOKEN_FALSO}", "ghp_" + "abcdefghijklmnopqrstuvwxyz0123456789")
# El token de ejemplo se arma en tiempo de ejecución: escrito entero en el
# archivo, el escaneo de secretos de GitHub lo confunde con uno real y puede
# bloquear el push de todo el repositorio.


def demo():
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        for nombre, contenido, debe_pasar in (("sano.yml", WF_SANO, True), ("roto.yml", WF_ROTO, False)):
            ruta = Path(tmp) / nombre
            ruta.write_text(contenido, encoding="utf-8")
            print("=" * 72)
            print(f"DEMO {nombre} — esperado: {'VERDE' if debe_pasar else 'ROJO'}")
            print("=" * 72)
            archivos, hallazgos, estado_al = auditar(ruta, usar_actionlint=False)
            imprimir(archivos, hallazgos, estado_al)
            bloquea = any(h["severidad"] in ("BLOQUEANTE", "MAYOR") for h in hallazgos)
            if bloquea == debe_pasar:
                ok = False
                print(">> DEMO FALLÓ: el resultado no coincide con lo esperado")
            print()
    print("AUTOTEST:", "OK" if ok else "FALLÓ")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="Gate CI/CD: antipatrones de GitHub Actions + actionlint")
    ap.add_argument("ruta", nargs="?", default=".github/workflows", help="carpeta o archivo de workflow")
    ap.add_argument("--demo", action="store_true", help="autotest con un workflow sano y uno roto")
    ap.add_argument("--json", action="store_true", help="salida JSON")
    ap.add_argument("--sin-actionlint", action="store_true", help="no correr actionlint aunque esté instalado")
    args = ap.parse_args()

    if args.demo:
        return demo()
    try:
        archivos, hallazgos, estado_al = auditar(args.ruta, usar_actionlint=not args.sin_actionlint)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"archivos": [str(a) for a in archivos], "actionlint": estado_al,
                          "hallazgos": hallazgos}, ensure_ascii=False, indent=2))
    else:
        imprimir(archivos, hallazgos, estado_al)
    return 1 if any(h["severidad"] in ("BLOQUEANTE", "MAYOR") for h in hallazgos) else 0


if __name__ == "__main__":
    sys.exit(main())
