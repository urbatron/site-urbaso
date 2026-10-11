#!/usr/bin/env node
/**
 * Rebuild responsive derivatives; originals are never modified.
 * Dependencies: Node 20+, sharp; Python 3, fonttools and brotli.
 * Install: npm install --no-save sharp; python3 -m pip install fonttools brotli
 * Run from any directory: node scripts/build-media.mjs
 * Output filenames include the first 12 hex characters of their SHA-256.
 * Keep the manifest and generated files in Git together with HTML/CSS changes.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { spawnSync } from 'node:child_process';
const require = createRequire(import.meta.url);
const sharp = require('sharp');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const out = path.join(root, 'assets/optimized');
const manifestPath = path.join(out, 'manifest.json');
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex').slice(0, 12);
const imageRecipe = 'sharp-lanczos3-webp-q90-doc94-lossless-v1';

// Approximate CSS widths from mobile/desktop layouts. Multiple resolutions
// allow the browser to retain 2x detail without sending desktop files to 1x.
const measured = {
  'hero/grid-paper-sheet.webp': [360, 400],
  'hero/sergeiurba_2.webp': [255, 532],
  'hero/website-wireframe-paper.webp': [219, 260],
  'hero/ad-dashboard_1000.webp': [205, 400],
  'hero/torn-paper-sheet.webp': [360, 520],
  'hero/lenta.webp': [175, 175],
  'hero/max-icon-round.webp': [56, 100],
  'hero/sticky-note-yellow-2.webp': [122, 215],
  'hero/sticky-note-krug.webp': [99, 175],
  'hero/punktir-2.webp': [27, 30],
  'hero/tape-short.webp': [62, 265],
  'hero/code.webp': [0, 300],
  'hero/orange-paper-shape.webp': [0, 165],
  'hero/blue-paper-shape.webp': [0, 180],
  'hero/up.webp': [0, 96],
  'hero/traffic-sources.webp': [0, 255],
  'hero/arrow-curved.webp': [0, 110],
  'hero/tape-diagonal.webp': [0, 59],
  'four/1.webp': [187, 360],
  'four/2.webp': [187, 260],
  'four/3.webp': [50, 135],
  'four/4.webp': [35, 96],
  'four/5.webp': [197, 360],
  'four/8.webp': [177, 320],
  'four/9.webp': [384, 920],
  'five/1.webp': [384, 640],
  'five/2.webp': [90, 100],
  'five/3.webp': [90, 100],
  'five/4.webp': [90, 100],
  'three/test.webp': [66, 170],
  'six/1.webp': [384, 280],
  'six/2.webp': [384, 280],
  'six/3.webp': [384, 280],
  'seven/3.webp': [153, 290],
  'seven/5.webp': [384, 620],
  'second/1.webp': [0, 250],
  'second/2.webp': [0, 110],
  'second/3.webp': [0, 75],
  'second/4.webp': [0, 130],
  'second/5.webp': [0, 165],
  'second/6.webp': [0, 175],
  'second/7.webp': [0, 90],
};

async function publish(bytes, directory, stem, extension) {
  const name = `${stem}-${hash(bytes)}.${extension}`;
  const target = path.join(out, directory, name);
  await fs.mkdir(path.dirname(target), { recursive: true });
  try { await fs.access(target); }
  catch { await fs.writeFile(target, bytes); }
  return '/' + path.relative(root, target).split(path.sep).join('/');
}

const previous = await fs.readFile(manifestPath, 'utf8').then(JSON.parse).catch(() => ({}));
const sources = new Set(Object.keys(previous.images || {}));
const html = await fs.readFile(path.join(root, 'index.html'), 'utf8');
for (const match of html.matchAll(/(?:\.?\/)?assets\/images\/[\w/.-]+\.webp/g)) {
  sources.add('/' + match[0].replace(/^\.?\//, ''));
}
for (const filename of await fs.readdir(path.join(root, 'assets/css'))) {
  if (!filename.endsWith('.css')) continue;
  const css = await fs.readFile(path.join(root, 'assets/css', filename), 'utf8');
  for (const match of css.matchAll(/url\(\s*['"]?([^)'"\s]+\.webp)(?:\?[^)'"\s]*)?['"]?\s*\)/g)) {
    const resolved = match[1].startsWith('/') ? match[1] :
      '/' + path.relative(root, path.resolve(root, 'assets/css', match[1])).split(path.sep).join('/');
    if (resolved.startsWith('/assets/images/')) sources.add(resolved);
  }
}

const manifest = {
  version: 1,
  description: 'Responsive derivatives of original Git assets. Keep original hrefs for document viewers.',
  images: {},
  fonts: {},
};

for (const src of [...sources].sort()) {
  const bytes = await fs.readFile(path.join(root, src.slice(1)));
  const info = await sharp(bytes).metadata();
  const relative = src.slice('/assets/images/'.length);
  const detailedPaper = ['hero/grid-paper-sheet.webp', 'four/1.webp', 'four/2.webp', 'four/8.webp'].includes(relative);
  const quality = detailedPaper ? 98 : (relative.startsWith('six/') || relative === 'seven/5.webp' ? 94 : 90);
  const recipe = imageRecipe + (detailedPaper ? '-paper98' : '');
  const cssWidths = measured[relative] || [Math.min(info.width, 384), Math.min(info.width, 640)];
  const widths = new Set([info.width]);
  for (const width of cssWidths.filter(Boolean)) {
    for (const scale of [1, 2]) widths.add(Math.min(info.width, Math.ceil(width * scale / 32) * 32));
  }
  const cached = previous.images?.[src];
  const cachedFilesExist = cached && (await Promise.all(cached.variants.map(v =>
    fs.access(path.join(root, v.src.slice(1))).then(() => true).catch(() => false)
  ))).every(Boolean);
  if (cachedFilesExist && cached.sourceHash === hash(bytes) && cached.recipe === recipe &&
      JSON.stringify(cached.requestedWidths) === JSON.stringify([...widths].sort((a, b) => a - b))) {
    manifest.images[src] = cached;
    continue;
  }
  const variants = [];
  for (const width of [...widths].sort((a, b) => a - b)) {
    let result = bytes;
    let encoding = 'original';
    if (width < info.width) {
      const pipeline = sharp(bytes).resize({ width, withoutEnlargement: true, kernel: 'lanczos3' });
      const lossless = await pipeline.clone().webp({ lossless: true, effort: 6 }).toBuffer();
      const highQuality = await pipeline.clone().webp({ quality, alphaQuality: 100, smartSubsample: true, effort: 6 }).toBuffer();
      result = lossless.length <= highQuality.length ? lossless : highQuality;
      encoding = result === lossless ? 'lossless' : `quality-${quality}`;
    }
    const finalInfo = await sharp(result).metadata();
    const generated = await publish(result, path.join('images', path.dirname(relative)), `${path.basename(relative, '.webp')}-${width}w`, 'webp');
    variants.push({ src: generated, width: finalInfo.width, height: finalInfo.height, bytes: result.length, encoding });
  }
  manifest.images[src] = {
    sourceHash: hash(bytes),
    recipe,
    original: { src, width: info.width, height: info.height, bytes: bytes.length },
    requestedWidths: [...widths].sort((a, b) => a - b),
    // A smaller derivative must never cost more than a sharper candidate.
    variants: variants.filter(v => !variants.some(other => other.width > v.width && other.bytes <= v.bytes)),
    suggestedSizes: { mobile: cssWidths[0], desktop: cssWidths[1] },
  };
}

// FontTools preserves the source outlines, metrics, variable axes, hinting and
// shaping features. Only unused script glyphs are removed. Include page/JS
// characters in addition to Latin/Western Latin, modern Cyrillic and punctuation.
const python = String.raw`
from pathlib import Path
from fontTools import subset
from fontTools.ttLib import TTFont
from html.parser import HTMLParser
import hashlib, io, json, sys
root = Path(sys.argv[1])
ranges = [(0x20,0x00ff),(0x0400,0x045f),(0x2000,0x206f)]
unicodes = set()
for lo,hi in ranges: unicodes.update(range(lo,hi+1))
text_sources = [root/'index.html', *sorted((root/'assets/js').glob('*.js')), *sorted((root/'assets/css').glob('*.css'))]
for p in text_sources: unicodes.update(map(ord,p.read_text(encoding='utf-8')))

# Only the handwritten labels need Caveat at first paint. Other characters
# remain available from the complete language subset through unicode-range.
class CaveatLabels(HTMLParser):
    roots = {'su-hero-v2__route','su-hero-v2__sticky','services','code-note',
             'su-services-v2__card','su-work-v1__script',
             'su-results-v1__fact-caption','su-results-v1__conclusion'}
    voids = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in self.voids: return
        classes = set(dict(attrs).get('class','').split())
        active = any(row[2] for row in self.stack) or bool(classes & self.roots)
        if tag == 'h3' and any('su-benefits-v1__primary-copy' in row[1] for row in self.stack): active = True
        self.stack.append((tag, classes, active))
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return
    def handle_data(self, data):
        if any(row[2] for row in self.stack): self.parts.append(data)
labels = CaveatLabels()
labels.feed((root/'index.html').read_text(encoding='utf-8'))
caveat_core = set(map(ord, ''.join(labels.parts) + ' \u00a0.,:;!?-–—«»()0123456789•'))

class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = False
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in {'script','style'}: self.skip = True
    def handle_endtag(self, tag):
        if tag in {'script','style'}: self.skip = False
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)
page_text = PageText()
page_text.feed((root/'index.html').read_text(encoding='utf-8'))
inter_core = set(map(ord, ''.join(page_text.parts))) | set(range(0x20,0x7f)) | set(range(0x410,0x450)) | {0x401,0x451}

def unicode_range(characters):
    values = sorted(characters)
    groups = []
    for cp in values:
        if groups and cp == groups[-1][1] + 1: groups[-1][1] = cp
        else: groups.append([cp,cp])
    return ','.join(f'U+{a:04X}' if a == b else f'U+{a:04X}-{b:04X}' for a,b in groups)
result = {}
for family, stem in [('Inter','inter-variable'),('Caveat','caveat-variable')]:
    source = root/'assets/fonts'/f'{stem}.woff2'
    font = TTFont(source, recalcTimestamp=False)
    original_cmap = font.getBestCmap()
    axes = [{ 'tag': a.axisTag, 'min': a.minValue, 'default': a.defaultValue, 'max': a.maxValue }
            for a in font['fvar'].axes]
    options = subset.Options()
    options.flavor = 'woff2'
    options.recalc_timestamp = False
    options.layout_features += ['tnum']
    options.name_IDs = ['*']
    options.name_languages = ['*']
    options.notdef_glyph = True
    options.notdef_outline = True
    sub = subset.Subsetter(options=options)
    sub.populate(unicodes=unicodes)
    sub.subset(font)
    buffer = io.BytesIO()
    font.save(buffer)
    data = buffer.getvalue()
    name = f'{stem}-latin-cyrillic-{hashlib.sha256(data).hexdigest()[:12]}.woff2'
    target = root/'assets/optimized/fonts'/name
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists(): target.write_bytes(data)
    check = TTFont(target)
    assert set(original_cmap).intersection(unicodes).issubset(check.getBestCmap())
    assert [(a.axisTag,a.minValue,a.maxValue) for a in check['fvar'].axes] == [(a['tag'],a['min'],a['max']) for a in axes]
    result[family] = {'src':'/'+str(target.relative_to(root)), 'bytes':len(data),
                      'originalBytes':source.stat().st_size, 'axes':axes,
                      'sourceGlyphs':len(original_cmap),'subsetGlyphs':len(check.getBestCmap())}
    if family in {'Inter','Caveat'}:
        core_characters = caveat_core if family == 'Caveat' else inter_core
        core = TTFont(target, recalcTimestamp=False)
        sub = subset.Subsetter(options=options)
        sub.populate(unicodes=core_characters)
        sub.subset(core)
        buffer = io.BytesIO()
        core.save(buffer)
        core_data = buffer.getvalue()
        core_name = f'{family.lower()}-variable-core-{hashlib.sha256(core_data).hexdigest()[:12]}.woff2'
        core_target = root/'assets/optimized/fonts'/core_name
        if not core_target.exists(): core_target.write_bytes(core_data)
        core_check = TTFont(core_target)
        assert set(original_cmap).intersection(core_characters).issubset(core_check.getBestCmap())
        assert [(a.axisTag,a.minValue,a.maxValue) for a in core_check['fvar'].axes] == [(a['tag'],a['min'],a['max']) for a in axes]
        result[family].update({'src':'/'+str(core_target.relative_to(root)), 'bytes':len(core_data),
                              'unicodeRange':unicode_range(core_check.getBestCmap()),
                              'subsetGlyphs':len(core_check.getBestCmap()),
                              'fallbackSrc':'/'+str(target.relative_to(root)), 'fallbackBytes':len(data)})
print(json.dumps(result))
`;
const fontBuild = spawnSync(process.env.PYTHON || 'python3', ['-c', python, root], { encoding: 'utf8' });
if (fontBuild.status !== 0) throw new Error(`Font build failed. Install fonttools and brotli.\n${fontBuild.stderr}`);
manifest.fonts = JSON.parse(fontBuild.stdout);
await fs.writeFile(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
console.log(`Built ${Object.keys(manifest.images).length} image families and ${Object.keys(manifest.fonts).length} font subsets.`);
console.log(`Manifest: ${path.relative(root, manifestPath)}`);
