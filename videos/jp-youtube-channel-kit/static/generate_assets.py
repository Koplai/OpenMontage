from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
ASSETS_DIR = ROOT.parent / "assets"

BRAND_CSS = dedent(
    """
    @font-face {
      font-family: 'Satoshi';
      src: url('../assets/satoshi-500.woff2') format('woff2');
      font-weight: 500;
      font-style: normal;
      font-display: swap;
    }
    @font-face {
      font-family: 'Satoshi';
      src: url('../assets/satoshi-700.woff2') format('woff2');
      font-weight: 700;
      font-style: normal;
      font-display: swap;
    }
    @font-face {
      font-family: 'Satoshi';
      src: url('../assets/satoshi-900.woff2') format('woff2');
      font-weight: 900;
      font-style: normal;
      font-display: swap;
    }

    :root {
      --navy: #0A1628;
      --azure: #4A90E2;
      --gold: #C4A35A;
      --ice: #F3F9FF;
      --white: #FFFFFF;
      --slate: #47607D;
      --ink: #131E2E;
      --line: rgba(74, 144, 226, 0.22);
      --line-strong: rgba(74, 144, 226, 0.4);
      --shadow: 0 18px 44px rgba(10, 22, 40, 0.18);
      --radius-xl: 34px;
      --radius-lg: 24px;
      --radius-md: 16px;
      --radius-sm: 12px;
    }

    * { box-sizing: border-box; }
    html, body {
      margin: 0;
      padding: 0;
      font-family: 'Satoshi', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      color: var(--white);
      background: var(--navy);
      width: 100%;
      height: 100%;
      overflow: hidden;
    }
    html.transparent, body.transparent {
      background: transparent;
    }
    .page {
      width: 100vw;
      height: 100vh;
      position: relative;
      overflow: hidden;
    }
    .bg-grid::before {
      content: '';
      position: absolute;
      inset: 0;
      background-image:
        linear-gradient(to right, rgba(74, 144, 226, 0.08) 1px, transparent 1px),
        linear-gradient(to bottom, rgba(74, 144, 226, 0.08) 1px, transparent 1px);
      background-size: 72px 72px;
      opacity: 0.6;
      pointer-events: none;
    }
    .grain::after {
      content: '';
      position: absolute;
      inset: 0;
      background:
        radial-gradient(circle at 15% 20%, rgba(255,255,255,0.06) 0, transparent 28%),
        radial-gradient(circle at 85% 15%, rgba(74,144,226,0.09) 0, transparent 28%),
        radial-gradient(circle at 75% 80%, rgba(196,163,90,0.08) 0, transparent 30%);
      pointer-events: none;
    }
    .eyebrow {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 8px 14px;
      border-radius: 999px;
      border: 1px solid rgba(255,255,255,0.12);
      background: rgba(19, 30, 46, 0.72);
      color: var(--ice);
      font-size: 18px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .eyebrow .dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--gold);
      box-shadow: 0 0 0 4px rgba(196, 163, 90, 0.16);
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(243,249,255,0.1);
      color: var(--ice);
      font-size: 15px;
      font-weight: 700;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      border: 1px solid rgba(255,255,255,0.12);
    }
    .mono {
      font-feature-settings: 'tnum' 1;
      font-variant-numeric: tabular-nums;
      letter-spacing: 0.03em;
    }
    .fit-box {
      position: relative;
      overflow: hidden;
    }
    .fit-text {
      position: relative;
      overflow: hidden;
      text-wrap: balance;
    }
    .callout-box {
      background: rgba(10, 22, 40, 0.88);
      border: 1px solid rgba(74, 144, 226, 0.24);
      box-shadow: var(--shadow);
      backdrop-filter: blur(0px);
    }
    .rule { height: 1px; background: rgba(255,255,255,0.14); width: 100%; }
    svg text { font-family: 'Satoshi', sans-serif; }
    """
)

LANG = {
    "es": {
        "series": "Serie técnica",
        "presenter_tag": "Presentador",
        "architecture_tag": "Arquitectura",
        "decision_tag": "Decisión",
        "banner_title": "IA en producción",
        "banner_sub": "Arquitectura, gobernanza y ROI sin humo",
        "lower_role": "Arquitectura de IA · Gobernanza · ROI",
        "callout_label": "Evidencia [E1]",
        "callout_source": "Fuente",
        "callout_scope": "Ámbito",
        "callout_date": "Fecha",
        "screen_title": "Demo técnico en vivo",
        "screen_mode": "Sesión guiada",
        "screen_meta": "Tenant · Flujo · Evidencia",
        "screen_footer": "Captura principal 16:9 · Mantener títulos y cursores dentro del marco",
        "contact_title": "JP YouTube Channel Kit · Static Review",
        "contact_sub": "Resumen visual de todas las familias estáticas",
    },
    "en": {
        "series": "Technical series",
        "presenter_tag": "Presenter",
        "architecture_tag": "Architecture",
        "decision_tag": "Decision",
        "banner_title": "AI in Production",
        "banner_sub": "Architecture, governance and ROI without hype",
        "lower_role": "AI Architecture · Governance · ROI",
        "callout_label": "Evidence [E1]",
        "callout_source": "Source",
        "callout_scope": "Scope",
        "callout_date": "Date",
        "screen_title": "Live technical demo",
        "screen_mode": "Guided session",
        "screen_meta": "Tenant · Workflow · Evidence",
        "screen_footer": "Primary 16:9 capture area · Keep titles and cursor movements inside frame",
        "contact_title": "JP YouTube Channel Kit · Static Review",
        "contact_sub": "Visual summary of every static family",
    },
}

TOPICS = {
    "architecture": {"es": "Arquitectura", "en": "Architecture", "accent": "#4A90E2"},
    "governance": {"es": "Gobernanza", "en": "Governance", "accent": "#C4A35A"},
    "security": {"es": "Seguridad", "en": "Security", "accent": "#7DB6FF"},
    "roi": {"es": "ROI", "en": "ROI", "accent": "#C4A35A"},
}

THUMBNAILS = [
    ("presenter", "es", "Copilot seguro"),
    ("presenter", "en", "Secure Copilot"),
    ("architecture", "es", "IA en producción"),
    ("architecture", "en", "AI in Production"),
    ("decision", "es", "Gobernanza que funciona"),
    ("decision", "en", "Governance That Works"),
]

CHAPTERS = [
    ("architecture", "es"), ("architecture", "en"),
    ("governance", "es"), ("governance", "en"),
    ("security", "es"), ("security", "en"),
    ("roi", "es"), ("roi", "en"),
]

DIAGRAMS = [
    ("reference-architecture", "es"), ("reference-architecture", "en"),
    ("governance-controls", "es"), ("governance-controls", "en"),
    ("roi-evidence", "es"), ("roi-evidence", "en"),
    ("decision-rule", "es"), ("decision-rule", "en"),
]


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def html_page(title: str, body: str, *, extra_style: str = "", transparent: bool = False) -> str:
    classes = "transparent" if transparent else ""
    return dedent(
        f"""
        <!doctype html>
        <html lang="en" class="{classes}">
          <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>{title}</title>
            <link rel="stylesheet" href="../brand.css" />
            <style>
            {extra_style}
            </style>
          </head>
          <body class="{classes}">
            {body}
          </body>
        </html>
        """
    )


def thumbnail_presenter(lang: str, title: str) -> str:
    copy = {
        "es": ("Arquitectura segura para IA real", "Copilot · Riesgo · Control"),
        "en": ("Secure architecture for real AI", "Copilot · Risk · Control"),
    }[lang]
    return html_page(
        f"thumbnail presenter {lang}",
        dedent(
            f"""
            <main class="page bg-grid grain presenter-thumb">
              <div class="left-col">
                <div class="eyebrow"><span class="dot"></span>{LANG[lang]['presenter_tag']}</div>
                <div class="fit-box title-box"><h1 class="fit-text" data-check="title">{title}</h1></div>
                <p class="subtitle" data-check="subtitle">{copy[0]}</p>
                <div class="meta-row">
                  <span class="badge">{copy[1]}</span>
                </div>
              </div>
              <div class="portrait-wrap">
                <div class="portrait-accent"></div>
                <div class="portrait-card">
                  <img src="../../assets/profile-photo.png" alt="Juan Pedro Márquez portrait" />
                  <div class="portrait-overlay"></div>
                </div>
                <div class="signature">JP</div>
              </div>
            </main>
            """
        ),
        extra_style=dedent(
            """
            .presenter-thumb { background: linear-gradient(145deg, #0A1628 0%, #131E2E 100%); }
            .left-col {
              position: absolute; left: 86px; top: 76px; width: 640px; z-index: 3;
            }
            .title-box { margin-top: 22px; width: 620px; min-height: 260px; }
            h1 {
              margin: 0; font-size: 96px; line-height: 0.94; font-weight: 900; letter-spacing: -0.04em;
            }
            .subtitle {
              margin: 18px 0 0; font-size: 32px; line-height: 1.16; color: rgba(243,249,255,0.88); width: 540px;
            }
            .meta-row { margin-top: 28px; }
            .portrait-wrap {
              position: absolute; right: 72px; top: 44px; width: 480px; height: 632px;
            }
            .portrait-accent {
              position: absolute; right: 42px; top: 32px; width: 388px; height: 488px; border-radius: 38px;
              background: linear-gradient(180deg, rgba(74,144,226,0.26), rgba(74,144,226,0.08));
              border: 1px solid rgba(74,144,226,0.28);
            }
            .portrait-card {
              position: absolute; right: 0; top: 0; width: 420px; height: 560px; border-radius: 42px;
              overflow: hidden; border: 1px solid rgba(255,255,255,0.08); box-shadow: var(--shadow);
              background: #131E2E;
            }
            .portrait-card img {
              width: 100%; height: 100%; object-fit: cover; object-position: center 20%; filter: saturate(0.9) contrast(1.03);
            }
            .portrait-overlay {
              position: absolute; inset: 0;
              background: linear-gradient(180deg, rgba(10,22,40,0.05) 0%, rgba(10,22,40,0.22) 72%, rgba(10,22,40,0.42) 100%);
            }
            .signature {
              position: absolute; left: 20px; bottom: 20px; width: 120px; height: 120px;
              border-radius: 24px; background: rgba(10,22,40,0.88); border: 1px solid rgba(196,163,90,0.36);
              color: var(--gold); display: grid; place-items: center; font-size: 56px; font-weight: 900; letter-spacing: -0.06em;
            }
            """
        ),
    )


def thumbnail_architecture(lang: str, title: str) -> str:
    labels = {
        "es": ["Usuarios", "Copilot", "Política", "Datos", "Logs", "Controles"],
        "en": ["Users", "Copilot", "Policy", "Data", "Logs", "Controls"],
    }[lang]
    subtitle = {
        "es": "Patrones que escalan sin teatro",
        "en": "Patterns that scale without theatre",
    }[lang]
    return html_page(
        f"thumbnail architecture {lang}",
        dedent(
            f"""
            <main class="page bg-grid grain architecture-thumb">
              <div class="left-col">
                <div class="eyebrow"><span class="dot"></span>{LANG[lang]['architecture_tag']}</div>
                <div class="fit-box title-box"><h1 class="fit-text" data-check="title">{title}</h1></div>
                <p class="subtitle" data-check="subtitle">{subtitle}</p>
              </div>
              <div class="diagram-card">
                <svg viewBox="0 0 520 420" aria-hidden="true">
                  <defs>
                    <marker id="arrow-arch" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
                      <path d="M0,0 L8,3 L0,6 Z" fill="#4A90E2" />
                    </marker>
                  </defs>
                  <rect x="36" y="28" width="448" height="364" rx="28" fill="#F3F9FF" stroke="#D8E4F6" />
                  <rect x="60" y="60" width="118" height="72" rx="18" fill="#0A1628" />
                  <text x="119" y="104" text-anchor="middle" font-size="22" font-weight="700" fill="#FFFFFF">{labels[0]}</text>
                  <rect x="200" y="60" width="120" height="72" rx="18" fill="#4A90E2" />
                  <text x="260" y="104" text-anchor="middle" font-size="22" font-weight="700" fill="#FFFFFF">{labels[1]}</text>
                  <rect x="344" y="60" width="116" height="72" rx="18" fill="#131E2E" />
                  <text x="402" y="104" text-anchor="middle" font-size="22" font-weight="700" fill="#FFFFFF">{labels[2]}</text>
                  <rect x="60" y="210" width="118" height="68" rx="18" fill="#FFFFFF" stroke="#C4A35A" stroke-width="2" />
                  <text x="119" y="252" text-anchor="middle" font-size="21" font-weight="700" fill="#131E2E">{labels[3]}</text>
                  <rect x="200" y="210" width="120" height="68" rx="18" fill="#FFFFFF" stroke="#4A90E2" stroke-width="2" />
                  <text x="260" y="252" text-anchor="middle" font-size="21" font-weight="700" fill="#131E2E">{labels[4]}</text>
                  <rect x="344" y="210" width="116" height="68" rx="18" fill="#FFFFFF" stroke="#131E2E" stroke-width="2" />
                  <text x="402" y="252" text-anchor="middle" font-size="20" font-weight="700" fill="#131E2E">{labels[5]}</text>
                  <line x1="178" y1="96" x2="200" y2="96" stroke="#4A90E2" stroke-width="4" marker-end="url(#arrow-arch)" />
                  <line x1="320" y1="96" x2="344" y2="96" stroke="#4A90E2" stroke-width="4" marker-end="url(#arrow-arch)" />
                  <line x1="260" y1="132" x2="260" y2="210" stroke="#4A90E2" stroke-width="4" marker-end="url(#arrow-arch)" />
                  <line x1="402" y1="132" x2="402" y2="210" stroke="#4A90E2" stroke-width="4" marker-end="url(#arrow-arch)" />
                </svg>
              </div>
            </main>
            """
        ),
        extra_style=dedent(
            """
            .architecture-thumb { background: linear-gradient(160deg, #0A1628 0%, #10213A 100%); }
            .left-col { position: absolute; left: 88px; top: 82px; width: 560px; z-index: 2; }
            .title-box { margin-top: 24px; width: 520px; min-height: 232px; }
            h1 { margin: 0; font-size: 92px; line-height: 0.96; font-weight: 900; letter-spacing: -0.04em; }
            .subtitle { margin: 18px 0 0; width: 480px; font-size: 30px; line-height: 1.18; color: rgba(243,249,255,0.88); }
            .diagram-card {
              position: absolute; right: 70px; top: 88px; width: 540px; height: 430px; border-radius: 32px;
              background: rgba(19,30,46,0.86); border: 1px solid rgba(255,255,255,0.08); box-shadow: var(--shadow);
              padding: 0; overflow: hidden;
            }
            .diagram-card::before {
              content: ''; position: absolute; inset: 18px; border-radius: 24px; border: 1px solid rgba(196,163,90,0.28); pointer-events: none;
            }
            .diagram-card svg { width: 100%; height: 100%; }
            """
        ),
    )


def thumbnail_decision(lang: str, title: str) -> str:
    labels = {
        "es": ("Evidencia", "Riesgo", "Control", "Decisión", "Listo para producción"),
        "en": ("Evidence", "Risk", "Control", "Decision", "Ready for production"),
    }[lang]
    return html_page(
        f"thumbnail decision {lang}",
        dedent(
            f"""
            <main class="page grain decision-thumb">
              <div class="left-col">
                <div class="eyebrow"><span class="dot"></span>{LANG[lang]['decision_tag']}</div>
                <div class="fit-box title-box"><h1 class="fit-text" data-check="title">{title}</h1></div>
                <p class="subtitle">{labels[4]}</p>
              </div>
              <div class="decision-panel">
                <div class="panel-header">{labels[3]}</div>
                <div class="panel-row"><span>{labels[0]}</span><strong class="mono">84 / 100</strong></div>
                <div class="panel-row"><span>{labels[1]}</span><strong class="mono">Bajo · Low</strong></div>
                <div class="panel-row"><span>{labels[2]}</span><strong class="mono">7 / 8</strong></div>
                <div class="confidence">
                  <div class="confidence-bar"><span style="width:82%"></span></div>
                  <div class="confidence-label">GO · APPROVED</div>
                </div>
              </div>
            </main>
            """
        ),
        extra_style=dedent(
            """
            .decision-thumb {
              background:
                linear-gradient(90deg, #0A1628 0%, #0A1628 65%, #F3F9FF 65%, #F3F9FF 100%);
            }
            .decision-thumb::before {
              content: ''; position: absolute; inset: 0;
              background-image: linear-gradient(to right, rgba(74,144,226,0.08) 1px, transparent 1px);
              background-size: 88px 88px; opacity: 0.6; pointer-events: none;
            }
            .left-col { position: absolute; left: 88px; top: 92px; width: 650px; z-index: 2; }
            .title-box { margin-top: 22px; width: 560px; min-height: 250px; }
            h1 { margin: 0; font-size: 90px; line-height: 0.94; font-weight: 900; letter-spacing: -0.045em; color: var(--white); }
            .subtitle { margin: 18px 0 0; color: rgba(243,249,255,0.88); font-size: 30px; }
            .decision-panel {
              position: absolute; right: 82px; top: 92px; width: 372px; padding: 30px 30px 26px;
              border-radius: 30px; background: #FFFFFF; color: #131E2E; box-shadow: 0 18px 44px rgba(10,22,40,0.16);
              border: 1px solid rgba(19,30,46,0.08);
            }
            .panel-header { font-size: 22px; font-weight: 900; letter-spacing: 0.08em; text-transform: uppercase; color: #47607D; }
            .panel-row {
              display: flex; justify-content: space-between; align-items: center; margin-top: 18px;
              padding: 16px 0; border-bottom: 1px solid rgba(19,30,46,0.08); font-size: 21px;
            }
            .panel-row strong { font-size: 21px; font-weight: 900; }
            .confidence { margin-top: 28px; }
            .confidence-bar { width: 100%; height: 16px; border-radius: 999px; overflow: hidden; background: rgba(74,144,226,0.12); }
            .confidence-bar span { display: block; height: 100%; border-radius: 999px; background: linear-gradient(90deg, #4A90E2, #C4A35A); }
            .confidence-label { margin-top: 14px; font-size: 30px; font-weight: 900; color: #0A1628; letter-spacing: -0.02em; }
            """
        ),
    )


def banner(lang: str) -> str:
    labels = {
        "es": ["Arquitectura", "Agentes", "Gobernanza", "ROI"],
        "en": ["Architecture", "Agents", "Governance", "ROI"],
    }[lang]
    principles = {
        "es": ["Claro", "Directo", "Con rigor"],
        "en": ["Clear", "Direct", "Rigorous"],
    }[lang]
    return html_page(
        f"clean banner {lang}",
        dedent(
            f"""
            <main class="page bg-grid grain clean-banner">
              <div class="safe-zone">
                <section class="copy">
                  <div class="eyebrow"><span class="dot"></span>Juan Pedro Márquez</div>
                  <h1 data-check="title">{LANG[lang]['banner_title']}</h1>
                  <p data-check="subtitle">{LANG[lang]['banner_sub']}</p>
                  <div class="topic-strip" aria-label="Channel topics">
                    <span>{labels[0]}</span>
                    <span>{labels[1]}</span>
                    <span>{labels[2]}</span>
                    <span>{labels[3]}</span>
                  </div>
                </section>
                <aside class="brand-statement">
                  <div class="jp-mark">JP</div>
                  <div class="statement-rule"></div>
                  <div class="principles">
                    <span>{principles[0]}</span>
                    <span>{principles[1]}</span>
                    <span>{principles[2]}</span>
                  </div>
                </aside>
              </div>
            </main>
            """
        ),
        extra_style=dedent(
            """
            .clean-banner { background: linear-gradient(135deg, #0A1628 0%, #131E2E 68%, #0F2037 100%); }
            .safe-zone {
              position: absolute; left: 507px; top: 509px; width: 1546px; height: 423px;
              display: grid; grid-template-columns: minmax(0, 1fr) 390px; gap: 72px; align-items: center;
              border-top: 1px solid rgba(74,144,226,0.18); border-bottom: 1px solid rgba(74,144,226,0.18);
            }
            .copy { min-width: 0; }
            .copy h1 {
              margin: 18px 0 0; max-width: 880px; font-size: 92px; line-height: 0.95; font-weight: 900; letter-spacing: -0.05em;
            }
            .copy p {
              margin: 16px 0 0; max-width: 860px; font-size: 32px; line-height: 1.16; color: rgba(243,249,255,0.86);
            }
            .topic-strip { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 24px; }
            .topic-strip span {
              padding: 8px 13px; border-radius: 999px;
              background: rgba(19,30,46,0.8); border: 1px solid rgba(74,144,226,0.24);
              color: rgba(243,249,255,0.92); font-size: 18px; font-weight: 700;
            }
            .brand-statement {
              height: 280px; display: grid; grid-template-columns: 150px 1px 1fr; gap: 28px; align-items: center;
            }
            .jp-mark {
              font-size: 112px; line-height: 1; font-weight: 900; letter-spacing: -0.09em;
              color: rgba(243,249,255,0.96);
            }
            .statement-rule { width: 1px; height: 190px; background: linear-gradient(180deg, #4A90E2, #C4A35A); }
            .principles { display: flex; flex-direction: column; gap: 18px; }
            .principles span {
              color: rgba(243,249,255,0.88); font-size: 20px; line-height: 1; font-weight: 700;
              letter-spacing: 0.08em; text-transform: uppercase;
            }
            """
        ),
    )


def banner_portrait(lang: str) -> str:
    labels = {
        "es": ["Arquitectura", "Gobernanza", "Seguridad", "ROI"],
        "en": ["Architecture", "Governance", "Security", "ROI"],
    }[lang]
    return html_page(
        f"banner {lang}",
        dedent(
            f"""
            <main class="page bg-grid grain banner-page">
              <div class="safe-zone">
                <section class="copy">
                  <div class="eyebrow"><span class="dot"></span>{LANG[lang]['series']}</div>
                  <h1 data-check="title">{LANG[lang]['banner_title']}</h1>
                  <p data-check="subtitle">{LANG[lang]['banner_sub']}</p>
                  <div class="topic-strip" aria-label="Channel topics">
                    <span>{labels[0]}</span>
                    <span>{labels[1]}</span>
                    <span>{labels[2]}</span>
                    <span>{labels[3]}</span>
                  </div>
                </section>
                <figure class="portrait-card">
                  <img src="../../assets/profile-photo.png" alt="Juan Pedro Márquez" />
                  <div class="portrait-shade"></div>
                  <figcaption>
                    <strong>Juan Pedro Márquez</strong>
                    <span>AI · Cloud · Copilot</span>
                  </figcaption>
                </figure>
              </div>
            </main>
            """
        ),
        extra_style=dedent(
            """
            .banner-page { background: linear-gradient(135deg, #0A1628 0%, #131E2E 68%, #0F2037 100%); }
            .safe-zone {
              position: absolute; left: 507px; top: 509px; width: 1546px; height: 423px;
              display: grid; grid-template-columns: minmax(0, 1fr) 520px; gap: 44px; align-items: center;
              border-top: 1px solid rgba(74,144,226,0.18); border-bottom: 1px solid rgba(74,144,226,0.18);
            }
            .copy { min-width: 0; }
            .copy h1 {
              margin: 18px 0 0; max-width: 860px; font-size: 92px; line-height: 0.95; font-weight: 900; letter-spacing: -0.05em;
            }
            .copy p {
              margin: 16px 0 0; max-width: 840px; font-size: 32px; line-height: 1.16; color: rgba(243,249,255,0.86);
            }
            .topic-strip {
              display: flex; flex-wrap: wrap; gap: 10px; margin-top: 24px;
            }
            .topic-strip span {
              padding: 8px 13px; border-radius: 999px;
              background: rgba(19,30,46,0.8); border: 1px solid rgba(74,144,226,0.24);
              color: rgba(243,249,255,0.92); font-size: 18px; font-weight: 700; letter-spacing: 0.01em;
            }
            .portrait-card {
              position: relative; width: 520px; height: 423px; margin: 0; overflow: hidden;
              border-radius: 30px; border: 1px solid rgba(255,255,255,0.11);
              background: #131E2E; box-shadow: var(--shadow);
            }
            .portrait-card img {
              width: 100%; height: 100%; object-fit: cover; object-position: 32% 28%;
              filter: saturate(0.88) contrast(1.04);
            }
            .portrait-shade {
              position: absolute; inset: 0;
              background:
                linear-gradient(90deg, rgba(10,22,40,0.18) 0%, transparent 42%),
                linear-gradient(180deg, transparent 52%, rgba(10,22,40,0.86) 100%);
            }
            .portrait-card figcaption {
              position: absolute; left: 26px; right: 26px; bottom: 22px;
              display: flex; align-items: flex-end; justify-content: space-between; gap: 18px;
            }
            .portrait-card strong { font-size: 22px; line-height: 1.1; font-weight: 900; }
            .portrait-card figcaption span {
              flex: 0 0 auto; color: var(--gold); font-size: 15px; font-weight: 700;
              letter-spacing: 0.05em; text-transform: uppercase;
            }
            """
        ),
    )


def avatar() -> str:
    return html_page(
        "avatar monogram",
        dedent(
            """
            <main class="page avatar-page">
              <div class="outer-ring">
                <div class="inner-disc">
                  <div class="grid"></div>
                  <div class="monogram"><span class="j">J</span><span class="divider"></span><span class="p">P</span></div>
                </div>
              </div>
            </main>
            """
        ),
        extra_style=dedent(
            """
            .avatar-page {
              display: grid; place-items: center;
              background: radial-gradient(circle at 50% 35%, #10213A 0%, #0A1628 62%, #08111F 100%);
            }
            .outer-ring {
              width: 660px; height: 660px; border-radius: 50%; padding: 16px;
              background: linear-gradient(135deg, rgba(196,163,90,0.95), rgba(74,144,226,0.92));
              box-shadow: 0 24px 60px rgba(10,22,40,0.28);
            }
            .inner-disc {
              position: relative; width: 100%; height: 100%; border-radius: 50%; overflow: hidden;
              background: linear-gradient(145deg, #0A1628 0%, #131E2E 100%);
              border: 1px solid rgba(255,255,255,0.08);
            }
            .grid {
              position: absolute; inset: 0;
              background-image:
                linear-gradient(to right, rgba(74,144,226,0.08) 1px, transparent 1px),
                linear-gradient(to bottom, rgba(74,144,226,0.08) 1px, transparent 1px);
              background-size: 52px 52px; mask-image: radial-gradient(circle, black 55%, transparent 88%);
            }
            .monogram {
              position: absolute; inset: 0; display: grid; place-items: center; grid-template-columns: auto 20px auto;
              gap: 18px; color: #FFFFFF;
            }
            .j, .p { font-size: 266px; line-height: 1; font-weight: 900; letter-spacing: -0.08em; }
            .j { color: #FFFFFF; transform: translateX(14px); }
            .p { color: #F3F9FF; transform: translateX(-12px); }
            .divider { width: 8px; height: 220px; border-radius: 999px; background: #C4A35A; box-shadow: 0 0 0 10px rgba(196,163,90,0.12); }
            """
        ),
    )


def avatar_portrait() -> str:
    return html_page(
        "avatar portrait",
        dedent(
            """
            <main class="page portrait-avatar-page">
              <div class="portrait-disc">
                <img src="../../assets/profile-photo.png" alt="Juan Pedro Márquez" />
                <div class="portrait-grade"></div>
                <div class="portrait-ring"></div>
              </div>
            </main>
            """
        ),
        extra_style=dedent(
            """
            .portrait-avatar-page {
              display: grid; place-items: center;
              background: radial-gradient(circle at 50% 32%, #19304D 0%, #0A1628 68%, #07101D 100%);
            }
            .portrait-disc {
              position: relative; width: 720px; height: 720px; border-radius: 50%; overflow: hidden;
              background: #131E2E; box-shadow: 0 24px 64px rgba(3,10,20,0.34);
            }
            .portrait-disc img {
              width: 100%; height: 100%; object-fit: cover; object-position: 31% 24%;
              transform: scale(1.22); transform-origin: 31% 24%;
              filter: saturate(0.92) contrast(1.04) brightness(1.02);
            }
            .portrait-grade {
              position: absolute; inset: 0;
              background:
                radial-gradient(circle at 48% 38%, transparent 0%, transparent 48%, rgba(10,22,40,0.18) 78%, rgba(10,22,40,0.38) 100%),
                linear-gradient(180deg, rgba(74,144,226,0.03), rgba(10,22,40,0.14));
            }
            .portrait-ring {
              position: absolute; inset: 0; border-radius: 50%;
              border: 14px solid transparent;
              background: linear-gradient(135deg, rgba(196,163,90,0.94), rgba(74,144,226,0.9)) border-box;
              mask: linear-gradient(#000 0 0) padding-box, linear-gradient(#000 0 0);
              mask-composite: exclude;
            }
            """
        ),
    )


def lower_third(lang: str) -> str:
    return html_page(
        f"lower third {lang}",
        dedent(
            f"""
            <main class="page lower-third-page">
              <div class="lower-third callout-box">
                <div class="badge-mark">JP</div>
                <div class="copy">
                  <div class="name" data-check="name">Juan Pedro Márquez</div>
                  <div class="role" data-check="role">{LANG[lang]['lower_role']}</div>
                </div>
              </div>
            </main>
            """
        ),
        transparent=True,
        extra_style=dedent(
            """
            .lower-third-page { background: transparent; }
            .lower-third {
              position: absolute; left: 88px; bottom: 84px; width: 1040px; height: 180px;
              border-radius: 30px; display: grid; grid-template-columns: 136px 1fr; align-items: center;
              padding: 0 36px 0 24px; overflow: hidden;
            }
            .lower-third::before {
              content: ''; position: absolute; inset: 0 auto 0 0; width: 14px; background: linear-gradient(180deg, #4A90E2, #C4A35A);
            }
            .badge-mark {
              width: 92px; height: 92px; border-radius: 24px; background: rgba(243,249,255,0.08);
              border: 1px solid rgba(196,163,90,0.28); display: grid; place-items: center; color: var(--gold);
              font-size: 42px; font-weight: 900; letter-spacing: -0.05em;
            }
            .copy { padding-left: 8px; }
            .name { font-size: 52px; font-weight: 900; letter-spacing: -0.03em; color: var(--white); }
            .role { margin-top: 8px; font-size: 28px; font-weight: 500; color: rgba(243,249,255,0.84); }
            """
        ),
    )


def evidence_callout(lang: str) -> str:
    scope = "Copilot / Security Review" if lang == "en" else "Copilot / Revisión de seguridad"
    return html_page(
        f"evidence callout {lang}",
        dedent(
            f"""
            <main class="page callout-page">
              <div class="evidence-box callout-box">
                <div class="eyebrow-row">
                  <span class="badge">{LANG[lang]['callout_label']}</span>
                </div>
                <div class="source-row"><span>{LANG[lang]['callout_source']}</span><strong class="mono">GitHub Audit Log · export.csv</strong></div>
                <div class="source-row"><span>{LANG[lang]['callout_scope']}</span><strong>{scope}</strong></div>
                <div class="source-row"><span>{LANG[lang]['callout_date']}</span><strong class="mono">2026-08-20</strong></div>
              </div>
            </main>
            """
        ),
        transparent=True,
        extra_style=dedent(
            """
            .callout-page { background: transparent; }
            .evidence-box {
              position: absolute; right: 88px; top: 88px; width: 620px; padding: 26px 28px 22px; border-radius: 28px;
            }
            .eyebrow-row { margin-bottom: 12px; }
            .source-row {
              display: flex; justify-content: space-between; align-items: baseline; gap: 20px;
              padding: 16px 0; border-bottom: 1px solid rgba(255,255,255,0.1); font-size: 22px; color: rgba(243,249,255,0.8);
            }
            .source-row:last-child { border-bottom: 0; padding-bottom: 6px; }
            .source-row strong { max-width: 360px; text-align: right; font-size: 22px; font-weight: 700; color: #FFFFFF; }
            """
        ),
    )


def chapter(topic_key: str, lang: str) -> str:
    title = TOPICS[topic_key][lang]
    accent = TOPICS[topic_key]["accent"]
    tag = LANG[lang]["series"]
    detail_map = {
        "architecture": {"es": "Patrones operables para IA empresarial", "en": "Operable patterns for enterprise AI"},
        "governance": {"es": "Controles claros, sin fricción teatral", "en": "Clear controls without performative friction"},
        "security": {"es": "Riesgo visible y mitigaciones verificables", "en": "Visible risk with verifiable mitigations"},
        "roi": {"es": "Valor medido con evidencia antes de escalar", "en": "Measured value with evidence before scale"},
    }
    detail = detail_map[topic_key][lang]
    svg = {
        "architecture": "<rect x='40' y='48' width='170' height='86' rx='22' fill='#0A1628'/><rect x='250' y='48' width='170' height='86' rx='22' fill='#4A90E2'/><rect x='145' y='194' width='170' height='86' rx='22' fill='#131E2E'/><line x1='210' y1='91' x2='250' y2='91' stroke='#4A90E2' stroke-width='6'/><line x1='230' y1='134' x2='230' y2='194' stroke='#C4A35A' stroke-width='6'/>" ,
        "governance": "<rect x='70' y='54' width='320' height='54' rx='18' fill='#0A1628'/><rect x='70' y='134' width='320' height='54' rx='18' fill='#131E2E'/><rect x='70' y='214' width='320' height='54' rx='18' fill='#4A90E2'/><line x1='230' y1='108' x2='230' y2='134' stroke='#C4A35A' stroke-width='6'/><line x1='230' y1='188' x2='230' y2='214' stroke='#C4A35A' stroke-width='6'/>" ,
        "security": "<rect x='90' y='54' width='280' height='72' rx='22' fill='#0A1628'/><rect x='90' y='154' width='280' height='72' rx='22' fill='#4A90E2'/><rect x='165' y='246' width='130' height='52' rx='16' fill='#131E2E'/><line x1='230' y1='126' x2='230' y2='154' stroke='#C4A35A' stroke-width='6'/><line x1='230' y1='226' x2='230' y2='246' stroke='#C4A35A' stroke-width='6'/>" ,
        "roi": "<rect x='74' y='228' width='54' height='72' rx='16' fill='#47607D'/><rect x='160' y='186' width='54' height='114' rx='16' fill='#4A90E2'/><rect x='246' y='134' width='54' height='166' rx='16' fill='#C4A35A'/><rect x='332' y='82' width='54' height='218' rx='16' fill='#FFFFFF'/><polyline points='96,214 186,170 272,122 358,70' fill='none' stroke='#C4A35A' stroke-width='6'/>" ,
    }[topic_key]
    return html_page(
        f"chapter {topic_key} {lang}",
        dedent(
            f"""
            <main class="page bg-grid grain chapter-page">
              <div class="chapter-rail" style="background:{accent}"></div>
              <div class="chapter-copy">
                <div class="eyebrow"><span class="dot"></span>{tag}</div>
                <h1 data-check="title">{title}</h1>
                <p data-check="subtitle">{detail}</p>
              </div>
              <div class="chapter-figure">
                <svg viewBox="0 0 460 340" aria-hidden="true">
                  <rect x="10" y="12" width="440" height="316" rx="30" fill="#F3F9FF" stroke="#D6E3F4" />
                  {svg}
                </svg>
              </div>
            </main>
            """
        ),
        extra_style=dedent(
            """
            .chapter-page { background: linear-gradient(145deg, #0A1628 0%, #131E2E 100%); }
            .chapter-rail { position: absolute; left: 80px; top: 110px; width: 14px; height: 860px; border-radius: 999px; }
            .chapter-copy { position: absolute; left: 126px; top: 146px; width: 760px; }
            .chapter-copy h1 { margin: 24px 0 0; font-size: 122px; line-height: 0.94; font-weight: 900; letter-spacing: -0.05em; }
            .chapter-copy p { margin: 22px 0 0; width: 680px; font-size: 34px; line-height: 1.18; color: rgba(243,249,255,0.84); }
            .chapter-figure {
              position: absolute; right: 90px; top: 196px; width: 540px; height: 400px; border-radius: 36px;
              background: rgba(19,30,46,0.76); border: 1px solid rgba(255,255,255,0.08); box-shadow: var(--shadow); overflow: hidden;
            }
            .chapter-figure svg { width: 100%; height: 100%; }
            """
        ),
    )


def diagram_reference_architecture(lang: str) -> str:
    t = {
        "es": {
            "title": "Arquitectura de referencia",
            "sub": "Identidad, políticas, datos y telemetría alineados en un flujo auditable.",
            "labels": ["Usuarios", "Copilot", "Entra ID", "Gateway de políticas", "Fuentes de datos", "Telemetría"],
        },
        "en": {
            "title": "Reference architecture",
            "sub": "Identity, policy, data and telemetry aligned in one auditable flow.",
            "labels": ["Users", "Copilot", "Entra ID", "Policy gateway", "Data sources", "Telemetry"],
        },
    }[lang]
    labels = t["labels"]
    svg = f"""
    <svg viewBox='0 0 980 660' aria-hidden='true'>
      <defs>
        <marker id='arrow-ref' markerWidth='12' markerHeight='12' refX='10' refY='4' orient='auto' markerUnits='strokeWidth'>
          <path d='M0,0 L10,4 L0,8 Z' fill='#4A90E2'/>
        </marker>
      </defs>
      <rect x='18' y='18' width='944' height='624' rx='34' fill='#FFFFFF' stroke='#D6E3F4'/>
      <rect x='70' y='90' width='180' height='84' rx='22' fill='#0A1628'/><text x='160' y='140' text-anchor='middle' font-size='30' font-weight='700' fill='#FFF'>{labels[0]}</text>
      <rect x='320' y='90' width='180' height='84' rx='22' fill='#4A90E2'/><text x='410' y='140' text-anchor='middle' font-size='30' font-weight='700' fill='#FFF'>{labels[1]}</text>
      <rect x='570' y='90' width='180' height='84' rx='22' fill='#131E2E'/><text x='660' y='140' text-anchor='middle' font-size='30' font-weight='700' fill='#FFF'>{labels[2]}</text>
      <rect x='320' y='270' width='180' height='84' rx='22' fill='#FFFFFF' stroke='#4A90E2' stroke-width='2.5'/><text x='410' y='320' text-anchor='middle' font-size='28' font-weight='700' fill='#131E2E'>{labels[3]}</text>
      <rect x='120' y='470' width='250' height='84' rx='22' fill='#FFFFFF' stroke='#C4A35A' stroke-width='2.5'/><text x='245' y='520' text-anchor='middle' font-size='28' font-weight='700' fill='#131E2E'>{labels[4]}</text>
      <rect x='450' y='470' width='250' height='84' rx='22' fill='#FFFFFF' stroke='#47607D' stroke-width='2.5'/><text x='575' y='520' text-anchor='middle' font-size='28' font-weight='700' fill='#131E2E'>{labels[5]}</text>
      <line x1='250' y1='132' x2='320' y2='132' stroke='#4A90E2' stroke-width='6' marker-end='url(#arrow-ref)'/>
      <line x1='500' y1='132' x2='570' y2='132' stroke='#4A90E2' stroke-width='6' marker-end='url(#arrow-ref)'/>
      <line x1='410' y1='174' x2='410' y2='270' stroke='#4A90E2' stroke-width='6' marker-end='url(#arrow-ref)'/>
      <line x1='410' y1='354' x2='245' y2='470' stroke='#4A90E2' stroke-width='6' marker-end='url(#arrow-ref)'/>
      <line x1='410' y1='354' x2='575' y2='470' stroke='#4A90E2' stroke-width='6' marker-end='url(#arrow-ref)'/>
    </svg>
    """
    return diagram_page(t["title"], t["sub"], svg, lang)


def diagram_governance_controls(lang: str) -> str:
    t = {
        "es": {
            "title": "Controles de gobernanza",
            "sub": "Capas de revisión y evidencia desde identidad hasta uso en producción.",
            "rows": ["Identidad", "Datos", "Prompts", "Observabilidad"],
            "cols": ["Política", "Revisión", "Prueba", "Evidencia"],
        },
        "en": {
            "title": "Governance controls",
            "sub": "Review and evidence layers from identity through production usage.",
            "rows": ["Identity", "Data", "Prompts", "Observability"],
            "cols": ["Policy", "Review", "Test", "Evidence"],
        },
    }[lang]
    cols = ''.join([f"<text x='{250 + i*150}' y='110' text-anchor='middle' font-size='24' font-weight='700' fill='#47607D'>{c}</text>" for i, c in enumerate(t['cols'])])
    rows = []
    y = 170
    fills = ["#0A1628", "#131E2E", "#4A90E2", "#47607D"]
    for idx, row in enumerate(t["rows"]):
        rows.append(f"<text x='135' y='{y+35}' text-anchor='middle' font-size='24' font-weight='700' fill='#131E2E'>{row}</text>")
        for i in range(4):
            fill = fills[i] if idx % 2 == 0 else "#F3F9FF"
            stroke = "none" if idx % 2 == 0 else "#D6E3F4"
            tx = 250 + i*150
            rows.append(f"<rect x='{tx-55}' y='{y}' width='110' height='58' rx='18' fill='{fill}' stroke='{stroke}'/>")
            txt_fill = '#FFFFFF' if idx % 2 == 0 else '#131E2E'
            rows.append(f"<text x='{tx}' y='{y+36}' text-anchor='middle' font-size='22' font-weight='700' fill='{txt_fill}'>✓</text>")
        y += 92
    svg = f"""
    <svg viewBox='0 0 980 660' aria-hidden='true'>
      <rect x='18' y='18' width='944' height='624' rx='34' fill='#FFFFFF' stroke='#D6E3F4'/>
      {cols}
      {''.join(rows)}
      <rect x='76' y='136' width='820' height='430' rx='30' fill='none' stroke='#E0E8F4'/>
    </svg>
    """
    return diagram_page(t["title"], t["sub"], svg, lang)


def diagram_roi_evidence(lang: str) -> str:
    t = {
        "es": {
            "title": "Evidencia de ROI",
            "sub": "Baseline, experimento, impacto medido y revisión financiera antes de escalar.",
            "labels": ["Baseline", "Experimento", "Impacto", "Finanzas", "Escalar"],
        },
        "en": {
            "title": "ROI evidence",
            "sub": "Baseline, experiment, measured impact and finance review before scale.",
            "labels": ["Baseline", "Experiment", "Impact", "Finance", "Scale"],
        },
    }[lang]
    xs = [120, 300, 480, 660, 840]
    boxes = []
    colors = ["#0A1628", "#131E2E", "#4A90E2", "#47607D", "#C4A35A"]
    for x, label, color in zip(xs, t['labels'], colors):
        boxes.append(f"<rect x='{x-80}' y='280' width='160' height='92' rx='24' fill='{color}'/><text x='{x}' y='335' text-anchor='middle' font-size='26' font-weight='700' fill='#FFF'>{label}</text>")
    arrows = ''.join([f"<line x1='{xs[i]+80}' y1='326' x2='{xs[i+1]-80}' y2='326' stroke='#4A90E2' stroke-width='6' marker-end='url(#arrow-roi)'/>" for i in range(4)])
    svg = f"""
    <svg viewBox='0 0 980 660' aria-hidden='true'>
      <defs>
        <marker id='arrow-roi' markerWidth='12' markerHeight='12' refX='10' refY='4' orient='auto' markerUnits='strokeWidth'>
          <path d='M0,0 L10,4 L0,8 Z' fill='#4A90E2'/>
        </marker>
      </defs>
      <rect x='18' y='18' width='944' height='624' rx='34' fill='#FFFFFF' stroke='#D6E3F4'/>
      <polyline points='120,472 300,420 480,366 660,318 840,252' fill='none' stroke='#C4A35A' stroke-width='8'/>
      <circle cx='120' cy='472' r='10' fill='#C4A35A'/><circle cx='300' cy='420' r='10' fill='#C4A35A'/><circle cx='480' cy='366' r='10' fill='#C4A35A'/><circle cx='660' cy='318' r='10' fill='#C4A35A'/><circle cx='840' cy='252' r='10' fill='#C4A35A'/>
      {''.join(boxes)}
      {arrows}
    </svg>
    """
    return diagram_page(t["title"], t["sub"], svg, lang)


def diagram_decision_rule(lang: str) -> str:
    t = {
        "es": {
            "title": "Regla de decisión",
            "sub": "Escalar solo cuando evidencia, riesgo y control pasan el umbral acordado.",
            "labels": ["Caso de uso", "¿Riesgo aceptable?", "¿Control listo?", "Piloto", "Escalar"],
            "yes": "Sí",
            "no": "No",
        },
        "en": {
            "title": "Decision rule",
            "sub": "Scale only when evidence, risk and control cross the agreed threshold.",
            "labels": ["Use case", "Acceptable risk?", "Control ready?", "Pilot", "Scale"],
            "yes": "Yes",
            "no": "No",
        },
    }[lang]
    l = t["labels"]
    svg = f"""
    <svg viewBox='0 0 980 660' aria-hidden='true'>
      <defs>
        <marker id='arrow-dec' markerWidth='12' markerHeight='12' refX='10' refY='4' orient='auto' markerUnits='strokeWidth'>
          <path d='M0,0 L10,4 L0,8 Z' fill='#4A90E2'/>
        </marker>
      </defs>
      <rect x='18' y='18' width='944' height='624' rx='34' fill='#FFFFFF' stroke='#D6E3F4'/>
      <rect x='390' y='70' width='200' height='86' rx='24' fill='#0A1628'/><text x='490' y='122' text-anchor='middle' font-size='28' font-weight='700' fill='#FFF'>{l[0]}</text>
      <polygon points='490,200 620,290 490,380 360,290' fill='#4A90E2'/><text x='490' y='300' text-anchor='middle' font-size='26' font-weight='700' fill='#FFF'>{l[1]}</text>
      <polygon points='760,200 900,290 760,380 620,290' fill='#131E2E'/><text x='760' y='300' text-anchor='middle' font-size='26' font-weight='700' fill='#FFF'>{l[2]}</text>
      <rect x='390' y='466' width='200' height='84' rx='24' fill='#47607D'/><text x='490' y='517' text-anchor='middle' font-size='28' font-weight='700' fill='#FFF'>{l[3]}</text>
      <rect x='720' y='466' width='180' height='84' rx='24' fill='#C4A35A'/><text x='810' y='517' text-anchor='middle' font-size='28' font-weight='700' fill='#0A1628'>{l[4]}</text>
      <line x1='490' y1='156' x2='490' y2='200' stroke='#4A90E2' stroke-width='6' marker-end='url(#arrow-dec)'/>
      <line x1='620' y1='290' x2='760' y2='290' stroke='#4A90E2' stroke-width='6' marker-end='url(#arrow-dec)'/>
      <line x1='490' y1='380' x2='490' y2='466' stroke='#4A90E2' stroke-width='6' marker-end='url(#arrow-dec)'/>
      <line x1='760' y1='380' x2='760' y2='466' stroke='#4A90E2' stroke-width='6' marker-end='url(#arrow-dec)'/>
      <text x='545' y='258' font-size='22' font-weight='700' fill='#47607D'>{t['yes']}</text>
      <text x='410' y='430' font-size='22' font-weight='700' fill='#47607D'>{t['no']}</text>
      <text x='815' y='430' font-size='22' font-weight='700' fill='#47607D'>{t['yes']}</text>
    </svg>
    """
    return diagram_page(t["title"], t["sub"], svg, lang)


def diagram_page(title: str, subtitle: str, svg: str, lang: str) -> str:
    return html_page(
        f"diagram {title}",
        dedent(
            f"""
            <main class="page bg-grid grain diagram-page">
              <div class="diagram-copy">
                <div class="eyebrow"><span class="dot"></span>{LANG[lang]['series']}</div>
                <h1 data-check="title">{title}</h1>
                <p data-check="subtitle">{subtitle}</p>
              </div>
              <div class="diagram-card">{svg}</div>
            </main>
            """
        ),
        extra_style=dedent(
            """
            .diagram-page { background: linear-gradient(145deg, #0A1628 0%, #131E2E 100%); }
            .diagram-copy { position: absolute; left: 88px; top: 88px; width: 820px; }
            .diagram-copy h1 { margin: 26px 0 0; font-size: 94px; line-height: 0.96; font-weight: 900; letter-spacing: -0.05em; }
            .diagram-copy p { margin: 18px 0 0; width: 760px; font-size: 32px; line-height: 1.18; color: rgba(243,249,255,0.84); }
            .diagram-card {
              position: absolute; left: 88px; right: 88px; bottom: 82px; top: 312px;
              border-radius: 36px; background: rgba(19,30,46,0.72); border: 1px solid rgba(255,255,255,0.08);
              box-shadow: var(--shadow); overflow: hidden;
            }
            .diagram-card svg { width: 100%; height: 100%; }
            """
        ),
    )


def screen_frame(lang: str) -> str:
    return html_page(
        f"screen frame {lang}",
        dedent(
            f"""
            <main class="page screen-frame-page">
              <div class="top-rail callout-box">
                <div class="left-stack">
                  <div class="rail-title">{LANG[lang]['screen_title']}</div>
                  <div class="rail-sub">{LANG[lang]['screen_mode']}</div>
                </div>
                <div class="badge mono">{LANG[lang]['screen_meta']}</div>
              </div>
              <div class="capture-window">
                <div class="corner tl"></div>
                <div class="corner tr"></div>
                <div class="corner bl"></div>
                <div class="corner br"></div>
              </div>
              <div class="bottom-rail callout-box">{LANG[lang]['screen_footer']}</div>
            </main>
            """
        ),
        transparent=True,
        extra_style=dedent(
            """
            .screen-frame-page { background: transparent; }
            .top-rail {
              position: absolute; left: 96px; right: 96px; top: 62px; height: 94px;
              border-radius: 24px; padding: 20px 26px; display: flex; justify-content: space-between; align-items: center;
            }
            .rail-title { font-size: 34px; font-weight: 900; letter-spacing: -0.03em; color: var(--white); }
            .rail-sub { margin-top: 4px; font-size: 20px; color: rgba(243,249,255,0.82); }
            .capture-window {
              position: absolute; left: 160px; top: 90px; width: 1600px; height: 900px;
              border: 2px solid rgba(74,144,226,0.6); border-radius: 26px;
            }
            .capture-window::before {
              content: ''; position: absolute; inset: 14px; border-radius: 18px; border: 1px dashed rgba(243,249,255,0.18);
            }
            .corner { position: absolute; width: 48px; height: 48px; border-color: #C4A35A; border-style: solid; }
            .tl { left: -2px; top: -2px; border-width: 4px 0 0 4px; border-top-left-radius: 24px; }
            .tr { right: -2px; top: -2px; border-width: 4px 4px 0 0; border-top-right-radius: 24px; }
            .bl { left: -2px; bottom: -2px; border-width: 0 0 4px 4px; border-bottom-left-radius: 24px; }
            .br { right: -2px; bottom: -2px; border-width: 0 4px 4px 0; border-bottom-right-radius: 24px; }
            .bottom-rail {
              position: absolute; left: 96px; right: 96px; bottom: 44px; min-height: 76px;
              border-radius: 22px; padding: 22px 26px; font-size: 22px; color: rgba(243,249,255,0.84);
            }
            """
        ),
    )


def contact_sheet_html() -> str:
    return html_page(
        "contact sheet",
        dedent(
            """
            <main class="page contact-page">
              <header class="header">
                <div class="eyebrow"><span class="dot"></span>Static system review</div>
                <h1>JP YouTube Channel Kit</h1>
                <p>Premium bilingual static identity — thumbnails, banner, avatar, overlays, chapters, diagrams and screen demo framing.</p>
              </header>
              <section class="grid">
                <article class="card wide">
                  <div class="card-head"><h2>Thumbnails</h2><span>3 systems · ES / EN</span></div>
                  <div class="thumb-row three-up">
                    <img src="thumbnails/presenter-es.png" alt="Presenter thumbnail" />
                    <img src="thumbnails/architecture-en.png" alt="Architecture thumbnail" />
                    <img src="thumbnails/decision-es.png" alt="Decision thumbnail" />
                  </div>
                </article>
                <article class="card wide">
                  <div class="card-head"><h2>Banner</h2><span>Editorial promise · safe zone centred</span></div>
                  <div class="banner-wrap"><img src="banner/channel-banner-en.png" alt="Channel banner" /></div>
                </article>
                <article class="card narrow avatar-card">
                  <div class="card-head"><h2>Avatar</h2><span>Personal portrait</span></div>
                  <div class="avatar-pair">
                    <img src="avatar/avatar-portrait.png" alt="Portrait avatar" />
                    <img src="avatar/avatar-monogram.png" alt="Monogram avatar" />
                  </div>
                </article>
                <article class="card wide overlay-card">
                  <div class="card-head"><h2>Overlays</h2><span>Transparent lower-third + callout</span></div>
                  <div class="overlay-preview">
                    <div class="preview-stage checker">
                      <img class="lt" src="overlays/lower-third-en.png" alt="Lower third" />
                      <img class="co" src="overlays/evidence-callout-en.png" alt="Evidence callout" />
                    </div>
                  </div>
                </article>
                <article class="card wide">
                  <div class="card-head"><h2>Chapter cards</h2><span>4 topics · ES / EN</span></div>
                  <div class="thumb-row four-up">
                    <img src="chapters/architecture-en.png" alt="Architecture chapter" />
                    <img src="chapters/governance-en.png" alt="Governance chapter" />
                    <img src="chapters/security-en.png" alt="Security chapter" />
                    <img src="chapters/roi-en.png" alt="ROI chapter" />
                  </div>
                </article>
                <article class="card wide">
                  <div class="card-head"><h2>Technical diagrams</h2><span>Reference architecture, controls, ROI, decision rule</span></div>
                  <div class="thumb-row four-up">
                    <img src="diagrams/reference-architecture-en.png" alt="Reference architecture" />
                    <img src="diagrams/governance-controls-en.png" alt="Governance controls" />
                    <img src="diagrams/roi-evidence-en.png" alt="ROI evidence" />
                    <img src="diagrams/decision-rule-en.png" alt="Decision rule" />
                  </div>
                </article>
                <article class="card wide">
                  <div class="card-head"><h2>Screen demo frame</h2><span>Transparent overlay</span></div>
                  <div class="screen-stage checker">
                    <div class="mock-screen"></div>
                    <img src="screen-frame/screen-demo-en.png" alt="Screen frame" />
                  </div>
                </article>
              </section>
            </main>
            """
        ),
        extra_style=dedent(
            """
            .contact-page { background: #F3F9FF; color: #131E2E; overflow: visible; min-height: 100vh; }
            .header { padding: 62px 76px 18px; color: #131E2E; }
            .header h1 { margin: 22px 0 0; font-size: 84px; line-height: 0.95; font-weight: 900; letter-spacing: -0.05em; }
            .header p { margin: 20px 0 0; width: 1600px; font-size: 28px; line-height: 1.2; color: #47607D; }
            .header .eyebrow { color: #131E2E; background: rgba(74,144,226,0.08); border-color: rgba(74,144,226,0.14); }
            .grid {
              padding: 24px 76px 84px; display: grid; grid-template-columns: 1.35fr 1fr; gap: 26px;
            }
            .card {
              background: #FFFFFF; border: 1px solid rgba(19,30,46,0.08); border-radius: 28px; box-shadow: 0 16px 40px rgba(10,22,40,0.08);
              padding: 22px 22px 24px; overflow: hidden;
            }
            .wide { grid-column: span 2; }
            .narrow { grid-column: span 1; }
            .card-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 16px; gap: 20px; }
            .card-head h2 { margin: 0; font-size: 30px; font-weight: 900; letter-spacing: -0.03em; }
            .card-head span { font-size: 16px; color: #47607D; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; }
            .thumb-row { display: grid; gap: 16px; }
            .three-up { grid-template-columns: repeat(3, minmax(0, 1fr)); }
            .four-up { grid-template-columns: repeat(4, minmax(0, 1fr)); }
            .thumb-row img, .banner-wrap img, .avatar-card img { width: 100%; display: block; border-radius: 20px; border: 1px solid rgba(19,30,46,0.08); }
            .banner-wrap img { border-radius: 26px; }
            .avatar-card { display: flex; flex-direction: column; }
            .avatar-pair { display: flex; gap: 22px; justify-content: center; align-items: center; }
            .avatar-card img { width: 240px; border-radius: 50%; }
            .overlay-preview { height: 360px; }
            .checker, .screen-stage { position: relative; border-radius: 22px; overflow: hidden; height: 100%; }
            .checker {
              background-image: linear-gradient(45deg, rgba(71,96,125,0.12) 25%, transparent 25%), linear-gradient(-45deg, rgba(71,96,125,0.12) 25%, transparent 25%), linear-gradient(45deg, transparent 75%, rgba(71,96,125,0.12) 75%), linear-gradient(-45deg, transparent 75%, rgba(71,96,125,0.12) 75%);
              background-size: 28px 28px; background-position: 0 0, 0 14px, 14px -14px, -14px 0px; background-color: #F6FAFF;
            }
            .preview-stage { position: relative; }
            .preview-stage img.lt { position: absolute; inset: auto auto 20px 18px; width: calc(100% - 36px); }
            .preview-stage img.co { position: absolute; top: 18px; right: 18px; width: 45%; }
            .screen-stage { height: 360px; display: grid; place-items: center; background: #EEF5FC; }
            .mock-screen { position: absolute; inset: 22px; border-radius: 22px; background: linear-gradient(145deg, #0A1628, #131E2E); }
            .screen-stage img { position: relative; width: 100%; height: 100%; object-fit: contain; }
            """
        ),
    )


def build_sources() -> list[dict]:
    write(ROOT / "brand.css", BRAND_CSS)
    specs = []
    for system, lang, title in THUMBNAILS:
        html = {
            "presenter": thumbnail_presenter,
            "architecture": thumbnail_architecture,
            "decision": thumbnail_decision,
        }[system](lang, title)
        base = ROOT / "thumbnails" / f"{system}-{lang}"
        write(base.with_suffix('.html'), html)
        specs.append({"html": base.with_suffix('.html'), "png": base.with_suffix('.png'), "width": 1280, "height": 720, "transparent": False})
    for lang in ["es", "en"]:
        base = ROOT / "banner" / f"channel-banner-{lang}"
        write(base.with_suffix('.html'), banner(lang))
        specs.append({"html": base.with_suffix('.html'), "png": base.with_suffix('.png'), "width": 2560, "height": 1440, "transparent": False})
        portrait_base = ROOT / "banner" / f"channel-banner-portrait-{lang}"
        write(portrait_base.with_suffix('.html'), banner_portrait(lang))
        specs.append({"html": portrait_base.with_suffix('.html'), "png": portrait_base.with_suffix('.png'), "width": 2560, "height": 1440, "transparent": False})
    base = ROOT / "avatar" / "avatar-monogram"
    write(base.with_suffix('.html'), avatar())
    specs.append({"html": base.with_suffix('.html'), "png": base.with_suffix('.png'), "width": 800, "height": 800, "transparent": False})
    base = ROOT / "avatar" / "avatar-portrait"
    write(base.with_suffix('.html'), avatar_portrait())
    specs.append({"html": base.with_suffix('.html'), "png": base.with_suffix('.png'), "width": 800, "height": 800, "transparent": False})
    for lang in ["es", "en"]:
        lt = ROOT / "overlays" / f"lower-third-{lang}"
        write(lt.with_suffix('.html'), lower_third(lang))
        specs.append({"html": lt.with_suffix('.html'), "png": lt.with_suffix('.png'), "width": 1920, "height": 1080, "transparent": True})
        ev = ROOT / "overlays" / f"evidence-callout-{lang}"
        write(ev.with_suffix('.html'), evidence_callout(lang))
        specs.append({"html": ev.with_suffix('.html'), "png": ev.with_suffix('.png'), "width": 1920, "height": 1080, "transparent": True})
    for topic, lang in CHAPTERS:
        base = ROOT / "chapters" / f"{topic}-{lang}"
        write(base.with_suffix('.html'), chapter(topic, lang))
        specs.append({"html": base.with_suffix('.html'), "png": base.with_suffix('.png'), "width": 1920, "height": 1080, "transparent": False})
    for diagram_key, lang in DIAGRAMS:
        builder = {
            "reference-architecture": diagram_reference_architecture,
            "governance-controls": diagram_governance_controls,
            "roi-evidence": diagram_roi_evidence,
            "decision-rule": diagram_decision_rule,
        }[diagram_key]
        base = ROOT / "diagrams" / f"{diagram_key}-{lang}"
        write(base.with_suffix('.html'), builder(lang))
        specs.append({"html": base.with_suffix('.html'), "png": base.with_suffix('.png'), "width": 1920, "height": 1080, "transparent": False})
    for lang in ["es", "en"]:
        base = ROOT / "screen-frame" / f"screen-demo-{lang}"
        write(base.with_suffix('.html'), screen_frame(lang))
        specs.append({"html": base.with_suffix('.html'), "png": base.with_suffix('.png'), "width": 1920, "height": 1080, "transparent": True})
    return specs


def render_assets(specs: list[dict]) -> list[str]:
    issues = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        try:
            for spec in specs:
                page = browser.new_page(viewport={"width": spec["width"], "height": spec["height"]}, device_scale_factor=1)
                page.goto(spec["html"].resolve().as_uri(), wait_until="load")
                page.wait_for_function("document.fonts && document.fonts.status === 'loaded'")
                page.wait_for_timeout(120)
                size = page.evaluate(
                    """
                    () => ({ width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight })
                    """
                )
                if size["width"] > spec["width"] or size["height"] > spec["height"]:
                    issues.append(f"Scroll overflow in {spec['html'].name}: {size}")
                fit_ok = page.evaluate(
                    """
                    () => {
                      const nodes = [...document.querySelectorAll('[data-check]')];
                      return nodes.map((node) => {
                        const r = node.getBoundingClientRect();
                        const p = node.parentElement.getBoundingClientRect();
                        return {
                          key: node.getAttribute('data-check'),
                          ok: r.left >= p.left - 0.5 && r.top >= p.top - 0.5 && r.right <= p.right + 0.5 && r.bottom <= p.bottom + 0.5,
                          html: node.innerText.trim()
                        };
                      });
                    }
                    """
                )
                for item in fit_ok:
                    if not item["ok"]:
                        issues.append(f"Fit check failed in {spec['html'].name} for {item['key']}: {item['html']}")
                page.screenshot(path=str(spec["png"]), omit_background=spec["transparent"])
                page.close()
        finally:
            browser.close()
    return issues


def build_contact_sheet() -> dict:
    html_path = ROOT / "contact-sheet.html"
    png_path = ROOT / "contact-sheet.png"
    write(html_path, contact_sheet_html())
    return {"html": html_path, "png": png_path, "width": 2560, "height": 4800, "transparent": False}


def render_contact_sheet(spec: dict) -> list[str]:
    issues = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": spec["width"], "height": spec["height"]}, device_scale_factor=1)
        try:
            page.goto(spec["html"].resolve().as_uri(), wait_until="load")
            page.wait_for_function("document.fonts && document.fonts.status === 'loaded'")
            page.wait_for_timeout(120)
            page.screenshot(path=str(spec["png"]))
        finally:
            page.close()
            browser.close()
    return issues


def build_readme() -> None:
    readme = dedent(
        """
        # JP YouTube Channel Kit · Static

        Premium bilingual YouTube identity system for Juan Pedro Márquez.

        ## Brand tokens

        - Deep Navy `#0A1628`
        - Azure `#4A90E2`
        - Gold `#C4A35A`
        - Ice `#F3F9FF`
        - White `#FFFFFF`
        - Slate `#47607D`
        - Ink `#131E2E`
        - Typography: local Satoshi weights 500 / 700 / 900 via `../assets/satoshi-{500,700,900}.woff2`
        - Portrait source: `../assets/profile-photo.png`

        ## Reproducibility

        - Source files are editable HTML files colocated with their PNG exports.
        - Shared tokens and fonts live in `brand.css`.
        - Regenerate all sources + PNGs with:

        ```bash
        python3 videos/jp-youtube-channel-kit/static/generate_assets.py
        ```

        ## Dimensions and safe zones

        | Family | Size | Safe guidance |
        |---|---:|---|
        | Thumbnails | 1280×720 | Keep the main title inside the left text column; maintain at least 72px outer margin. |
        | Banner | 2560×1440 | Critical content stays inside the centred 1546×423 safe zone (x: 507–2053, y: 509–932). |
        | Avatar | 800×800 | Portrait and monogram variants keep critical content inside the circular crop. |
        | Lower-third | 1920×1080 | Transparent canvas; live plate anchored bottom-left within 88px margins. |
        | Evidence callout | 1920×1080 | Transparent canvas; floating box anchored top-right within 88px margins. |
        | Chapter cards | 1920×1080 | Main title block sits left, figure block right; both stay inside 80–90px margins. |
        | Technical diagrams | 1920×1080 | Diagram card spans between 88px side margins and below a 312px title band. |
        | Screen demo frame | 1920×1080 | Transparent overlay with a 1600×900 central capture window (16:9) at x: 160–1760, y: 90–990. |
        | Contact sheet | 2560×4800 | Review sheet only. |

        ## Localization rules

        - Keep layout structure identical between Spanish and English siblings.
        - Use the provided canonical copy for banner, lower-third role, chapter titles, and thumbnail titles.
        - Do not mix languages within a localized asset except product or platform names (for example `Copilot`, `Entra ID`, `ROI`).
        - Preserve title case in English and sentence-style capitalization in Spanish exactly as exported.

        ## File inventory

        ### thumbnails/
        - `presenter-es.html` / `presenter-es.png`
        - `presenter-en.html` / `presenter-en.png`
        - `architecture-es.html` / `architecture-es.png`
        - `architecture-en.html` / `architecture-en.png`
        - `decision-es.html` / `decision-es.png`
        - `decision-en.html` / `decision-en.png`

        ### banner/
        - `channel-banner-es.html` / `channel-banner-es.png`
        - `channel-banner-en.html` / `channel-banner-en.png`
        - `channel-banner-portrait-es.html` / `channel-banner-portrait-es.png`
        - `channel-banner-portrait-en.html` / `channel-banner-portrait-en.png`

        ### avatar/
        - `avatar-monogram.html` / `avatar-monogram.png`
        - `avatar-portrait.html` / `avatar-portrait.png`

        ### overlays/
        - `lower-third-es.html` / `lower-third-es.png`
        - `lower-third-en.html` / `lower-third-en.png`
        - `evidence-callout-es.html` / `evidence-callout-es.png`
        - `evidence-callout-en.html` / `evidence-callout-en.png`

        ### chapters/
        - `architecture-es.html` / `architecture-es.png`
        - `architecture-en.html` / `architecture-en.png`
        - `governance-es.html` / `governance-es.png`
        - `governance-en.html` / `governance-en.png`
        - `security-es.html` / `security-es.png`
        - `security-en.html` / `security-en.png`
        - `roi-es.html` / `roi-es.png`
        - `roi-en.html` / `roi-en.png`

        ### diagrams/
        - `reference-architecture-es.html` / `reference-architecture-es.png`
        - `reference-architecture-en.html` / `reference-architecture-en.png`
        - `governance-controls-es.html` / `governance-controls-es.png`
        - `governance-controls-en.html` / `governance-controls-en.png`
        - `roi-evidence-es.html` / `roi-evidence-es.png`
        - `roi-evidence-en.html` / `roi-evidence-en.png`
        - `decision-rule-es.html` / `decision-rule-es.png`
        - `decision-rule-en.html` / `decision-rule-en.png`

        ### screen-frame/
        - `screen-demo-es.html` / `screen-demo-es.png`
        - `screen-demo-en.html` / `screen-demo-en.png`

        ### root
        - `brand.css`
        - `generate_assets.py`
        - `contact-sheet.html`
        - `contact-sheet.png`
        - `README.md`
        - `render-report.json`
        """
    )
    write(ROOT / "README.md", readme)


def main() -> None:
    specs = build_sources()
    issues = render_assets(specs)
    contact = build_contact_sheet()
    issues.extend(render_contact_sheet(contact))
    build_readme()
    report = {
        "assets": [
            {
                "html": str(spec["html"].relative_to(ROOT)),
                "png": str(spec["png"].relative_to(ROOT)),
                "width": spec["width"],
                "height": spec["height"],
                "transparent": spec["transparent"],
            }
            for spec in specs
        ] + [
            {
                "html": str(contact["html"].relative_to(ROOT)),
                "png": str(contact["png"].relative_to(ROOT)),
                "width": contact["width"],
                "height": contact["height"],
                "transparent": contact["transparent"],
            }
        ],
        "issues": issues,
    }
    write(ROOT / "render-report.json", json.dumps(report, indent=2))
    if issues:
        raise SystemExit("\n".join(issues))


if __name__ == "__main__":
    main()
