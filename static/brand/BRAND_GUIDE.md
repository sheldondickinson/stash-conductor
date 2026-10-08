# Stash Conductor visual guide


Use the supplied four artwork masters in `assets/brand/` as visual references and production raster sources. They are generated raster artwork, not editable vector files; do not claim otherwise. The symbol is two interlocking mint/orange storage tubs forming an S. Retain the identity rather than substitute a generic box icon.

| Design token | Hex | Intended use |
| --- | --- | --- |
| Brand mint/green | **#75D8BB** | Upper emblem, selected accents, soft highlights |
| Brand warm orange | **#FFAD66** | Lower emblem, capture accents, illustration detail |
| Deep ink | **#172B32** | Primary text, dark surfaces, icon background |
| Warm ivory | **#F6F2EA** | Main light background |
| White | **#FFFFFF** | Cards, input surfaces, reversed text where contrast passes |
| Muted slate | **#52666C** | Secondary text |
| Light border | **#D9E2DE** | Dividers and input borders |
| Dark green | **#16644F** | Strong green controls and text where verified accessible |
| Dark rust | **#9B4B13** | Strong orange-family text/controls |
| Error red | **#B93838** | Errors/destructive actions, always accompanied by text/icon |

These are canonical UI tokens. Raster artwork may contain shading and colour variation. Use deep ink text on mint/orange; do not assume white text on these pastel brand colours is legible. Verify contrast, focus indicators and dark-mode tokens; never rely on colour alone for state.

Use a friendly geometric sans-serif (e.g. self-hosted Manrope with its licence, or a suitable existing licensed font), clear headings, generous spacing, restrained rounded cards and large touch targets around 44–48 CSS px. Avoid cluttered admin tables as the mobile default. Prioritise Find, Add and Containers. The active tub should remain unmistakable during capture. Use photos generously and metadata progressively.

Use the wordmark on light surfaces; for dark mode prepare a proper light wordmark variant while retaining the mark. Preserve originals. Clean/vectorise the simple mark if needed, checking shape fidelity and crisp small-size rendering. Export real favicon files (16/32/48 where appropriate), apple-touch-icon, PWA 192/512 icons and separately checked maskable artwork. Do not embed a large PNG in an SVG and call it an editable vector. Check icon safe areas and readability at actual size.

The banner is for landing/about/docs/social contexts. In app pages use real HTML text and responsive layouts rather than an image containing all the controls or headline text. The transparent tub illustration suits onboarding/empty inventory. Supply meaningful alt text where informative and empty alt where decorative. Do not generate fake QR codes; labels must carry valid application URLs/codes.


## Source artwork

The four PNG masters were generated for this project with OpenAI image generation on 9 October 2026. They are raster originals, not SVG or final browser icon exports. Preserve them and produce optimised derivatives during implementation. Palette tokens are exact targets; image colours may vary. No existing font file is included; select and license the UI font separately. The pictured electronics are decorative illustrations, not technical diagrams.
