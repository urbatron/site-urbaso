# Responsive images and font subsets

`build-media.mjs` builds derivatives in `assets/optimized/` and a manifest for
the HTML/CSS build. Original files in `assets/images/` and `assets/fonts/` are
never changed. Document viewer links must continue pointing to the original
full-resolution documents.

## Dependencies and build

- Node.js 20 or newer and `sharp`.
- Python 3 with `fonttools` and `brotli` (WOFF2 support).

Install these in the development environment, then run from the repository:

```sh
npm install --no-save --package-lock=false sharp
python3 -m pip install fonttools brotli
node scripts/build-media.mjs
```

If Python dependencies are in a virtual environment, select its interpreter:

```sh
PYTHON=/path/to/venv/bin/python node scripts/build-media.mjs
```

No media build is required on the production server. Commit the generated
assets, manifest and corresponding HTML/CSS changes together. Rebuild the
HTML/CSS after rebuilding media because content hashes may have changed.

## Output and quality

- Every generated URL includes a 12-character SHA-256 prefix for immutable
  caching. The script does not overwrite or delete previous hashed files.
- Image candidates cover the measured mobile/desktop CSS widths at 1x/2x,
  capped at the original resolution. Unchanged full-size candidates preserve
  the exact original bytes.
- Smaller images use Lanczos3 resizing. The smaller of lossless and high-quality
  WebP is retained. Default quality is 90, document previews use 94 and the
  detailed first-screen/results paper textures use 98; alpha quality is 100.
- Candidates larger in bytes than a higher-resolution candidate are excluded
  from the manifest. Sources and recipe metadata allow unchanged image
  families to be reused on subsequent builds.
- Font subsets preserve Latin/Western Latin, modern Cyrillic, punctuation,
  and all characters present in HTML, JavaScript and CSS. Original font axes,
  metrics, kerning, normal shaping and tabular numbers are retained.
- Inter has a smaller core with ASCII, the complete Russian alphabet and current
  page text. Caveat's core covers the current handwritten labels, collected
  from HTML during the build. Each `unicodeRange` lets the browser use the full
  language subset from `fallbackSrc` for any other character. Emit the fallback
  face first and the core face second, with the same family/style/weight; only
  the core face receives `unicode-range`. Keep both files when pruning outputs.
- When adding another language, extend the font character ranges in the script.
  The normal site build must still check layout and real device image selection.

The manifest maps each original image URL to its dimensions and ordered
`variants` (`src`, `width`, `height`, `bytes`). `suggestedSizes` is a build hint;
HTML `sizes` must match the actual component CSS. The `fonts` map is keyed by
`Inter` and `Caveat`.
