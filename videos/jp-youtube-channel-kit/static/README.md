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
- Casual avatar source: `../assets/casual-profile.png`

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
