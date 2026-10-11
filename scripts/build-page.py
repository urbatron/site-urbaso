#!/usr/bin/env python3
"""Update image/font references after build-media.mjs and build-css.py.

Usage: python3 scripts/build-page.py --stylesheet /assets/optimized/site-HASH.css
Original document links are deliberately left unchanged. No runtime dependency.
"""
import argparse
import html
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]


class Attributes(HTMLParser):
    def handle_starttag(self, tag, attrs):
        self.attrs = dict(attrs)


def source_path(src):
    src = '/' + src.removeprefix('./').lstrip('/')
    return re.sub(r'^/assets/optimized/images/(.+)-\d+w-[a-f0-9]{12}\.webp$',
                  r'/assets/images/\1.webp', src)


def image_sizes(src, entry, lazy):
    mobile = max(1, entry['suggestedSizes']['mobile'])
    desktop = max(mobile, entry['suggestedSizes']['desktop'])
    if src.endswith('/hero/grid-paper-sheet.webp'):
        fallback = '(max-width: 767px) min(calc(100vw - 36px), 360px), 400px'
    elif src.endswith('/hero/sergeiurba_2.webp'):
        fallback = '(max-width: 767px) min(74vw, 255px), 532px'
    else:
        fallback = f'(max-width: 767px) min(100vw, {mobile}px), {desktop}px'
    # Native auto sizes uses the actual rendered width of a lazy image. The
    # explicit fallbacks support browsers that do not implement auto sizes.
    return ('auto, ' if lazy else '') + fallback


def update_first_screen_hints(text):
    # Replace only the two generated blocks so rebuilding never duplicates them.
    for name, indent in [('hero-mobile-preload', '  '), ('hero-desktop-prepaint', '      ')]:
        text = re.sub(
            rf'{indent}<!-- {name}:start -->\n.*?{indent}<!-- {name}:end -->\n',
            '', text, flags=re.S)

    paper_tags = re.findall(r'<img\b[^>]*\bclass="grid-paper-top"[^>]*>', text)
    if len(paper_tags) != 1:
        raise ValueError('Expected one critical hero paper image')
    parser = Attributes()
    parser.feed(paper_tags[0])
    paper = parser.attrs
    # Use the exact responsive candidates of the visible image, including its
    # fallback, to avoid a second download or a change in selected resolution.
    preload_attrs = {
        'rel': 'preload', 'as': 'image', 'href': paper['src'],
        'imagesrcset': paper['srcset'], 'imagesizes': paper['sizes'],
        'media': '(max-width: 767px)', 'fetchpriority': 'high',
    }
    preload = ('  <!-- hero-mobile-preload:start -->\n  <link' + ''.join(
        f' {key}="{html.escape(value, quote=True)}"'
        for key, value in preload_attrs.items()) +
        '>\n  <!-- hero-mobile-preload:end -->\n')
    font_preload = re.search(r'  <link rel="preload"[^>]* as="font"[^>]*>', text)
    if not font_preload:
        raise ValueError('Expected a font preload insertion point')
    text = text[:font_preload.start()] + preload + text[font_preload.start():]

    # Desktop geometry depends only on viewport dimensions. Set it before the
    # hero children can paint; the existing runtime still owns resize, tablet
    # measurements and the normal initialization fallback.
    prepaint = '''      <!-- hero-desktop-prepaint:start -->
      <script>
        (() => {
          if (innerWidth < 1280) return;
          const hero = document.currentScript.parentElement;
          const stage = Math.min(innerWidth, 1536);
          const fluid = Math.min(1, Math.max(0, (stage - 1280) / 256));
          const left = 640 + 140 * fluid;
          hero.classList.toggle('su-hero-v2--short', innerHeight < 800);
          hero.style.setProperty('--hero-stage-width', `${stage}px`);
          hero.style.setProperty('--hero-left-column', `${left}px`);
          hero.style.setProperty('--hero-artboard-scale',
            String(Math.min(1, Math.max(0, stage - left) / 756)));
          hero.style.setProperty('--hero-fluid', String(fluid));
        })();
      </script>
      <!-- hero-desktop-prepaint:end -->
'''
    section = '    <section id="su-hero-v2" class="su-hero-v2">\n'
    if text.count(section) != 1:
        raise ValueError('Expected one hero section insertion point')
    return text.replace(section, section + prepaint, 1)


def build(stylesheet):
    assert re.fullmatch(r'/assets/optimized/site-[a-f0-9]{12}\.css', stylesheet)
    if not (ROOT / stylesheet.lstrip('/')).is_file():
        raise FileNotFoundError(stylesheet)
    manifest = json.loads((ROOT / 'assets/optimized/manifest.json').read_text())
    page = ROOT / 'index.html'
    text = page.read_text()
    # The site is a single page. Sending its exact stylesheet with the HTML
    # avoids a render-blocking request on the current HTTP/1.1 origin.
    inline_styles = (r'  <!-- site-styles:start -->\n'
                     r'  <style data-source="/assets/optimized/site-[a-f0-9]{12}\.css">'
                     r'.*?</style>\n  <!-- site-styles:end -->\n')
    text, previous_inline_styles = re.subn(inline_styles, '', text, flags=re.S)
    if previous_inline_styles > 1:
        raise ValueError('Duplicate generated stylesheets')
    hero_end = text.index('</section>')
    critical = {'grid-paper-top', 'grid', 'portrait'}
    count = 0

    def update_image(match):
        nonlocal count
        parser = Attributes()
        parser.feed(match.group())
        attrs = parser.attrs
        if not attrs.get('src') or re.match(r'(https?:|data:)', attrs['src']):
            return match.group()
        src = source_path(attrs['src'])
        in_hero = match.start() < hero_end
        in_dialog = text.rfind('<dialog', 0, match.start()) > text.rfind('</dialog>', 0, match.start())
        is_critical = in_hero and attrs.get('class') in critical
        lazy = not is_critical
        if src in manifest['images']:
            entry = manifest['images'][src]
            variants = entry['variants']
            target_width = min(entry['original']['width'], max(1, entry['suggestedSizes']['desktop']))
            fallback = next((v for v in variants if v['width'] >= target_width), variants[-1])
            attrs['src'] = fallback['src']
            attrs['srcset'] = ', '.join(f"{v['src']} {v['width']}w" for v in variants)
            attrs['sizes'] = image_sizes(src, entry, lazy)
            attrs['width'] = str(entry['original']['width'])
            attrs['height'] = str(entry['original']['height'])
            if in_dialog:
                # Viewers change src when a document is selected. A persistent
                # preview srcset would override that selection and blur zoom.
                attrs['src'] = src
                attrs.pop('srcset', None)
                attrs.pop('sizes', None)
            elif attrs.get('class') == 'portrait':
                # Preserve facial detail at every pixel density; priority and
                # reduced competing requests matter more than these few KB.
                attrs['src'] = variants[-1]['src']
                attrs.pop('srcset', None)
                attrs.pop('sizes', None)
            elif attrs.get('class') == 'su-work-v1__underline':
                # This inline-block heading depends on the original intrinsic
                # width. Auto sizes would introduce containment and shrink it.
                attrs['src'] = src
                attrs.pop('srcset', None)
                attrs.pop('sizes', None)
        elif src.endswith('.svg'):
            svg = ET.parse(ROOT / src.lstrip('/')).getroot()
            viewbox = svg.attrib.get('viewBox', '').split()
            if len(viewbox) == 4:
                attrs['width'] = str(round(float(viewbox[2])))
                attrs['height'] = str(round(float(viewbox[3])))
        attrs['loading'] = 'lazy' if lazy else 'eager'
        attrs['decoding'] = 'async'
        if is_critical:
            attrs['fetchpriority'] = 'high'
        else:
            attrs.pop('fetchpriority', None)
        count += 1
        return '<img' + ''.join(' ' + key + ('' if value is None else '="' + html.escape(value, quote=True) + '"') for key, value in attrs.items()) + '>'

    text = re.sub(r'<img\b[^>]*>', update_image, text)
    # Preload the same hashed FAQ artwork that the bundled CSS uses, and only
    # when that section approaches the viewport (see su-situations-v1.js).
    for number in range(1, 5):
        entry = manifest['images'][f'/assets/images/eight/{number}_blue.webp']
        active = max(entry['variants'], key=lambda item: item['width'])['src']
        def update_tab(match):
            tag = re.sub(r' data-active-image="[^"]*"', '', match.group())
            return tag[:-1] + f' data-active-image="{active}">'
        text, matched = re.subn(rf'<button\b[^>]*\bid="su-situation-tab-{number}"[^>]*>', update_tab, text)
        if matched != 1:
            raise ValueError(f'Expected one FAQ tab {number}')

    # Replace only stylesheets owned by this static site's build.
    styles = r'  <link rel="stylesheet" href="(?:\./assets/css/[^\"]+|/assets/optimized/site-[a-f0-9]{12}\.css)">\n'
    text, replaced = re.subn(styles, '', text)
    if not replaced and not previous_inline_styles:
        raise ValueError('No expected stylesheet to update')
    if replaced and previous_inline_styles:
        raise ValueError('Both inline and external generated stylesheets found')
    css = (ROOT / stylesheet.lstrip('/')).read_text()
    if re.search(r'</style', css, flags=re.I):
        raise ValueError('Stylesheet contains an HTML style closing tag')
    styles_block = (f'  <!-- site-styles:start -->\n'
                    f'  <style data-source="{stylesheet}">{css}</style>\n'
                    f'  <!-- site-styles:end -->\n')
    text = text.replace('  <!-- Yandex.Metrika counter -->',
                        styles_block + '  <!-- Yandex.Metrika counter -->', 1)
    for family, stem in [('Inter', 'inter'), ('Caveat', 'caveat')]:
        text, replaced = re.subn(
            r'(<link rel="preload" href=")[^\"]*/' + stem + r'-[^\"]+\.woff2(" as="font")',
            lambda m: m.group(1) + manifest['fonts'][family]['src'] + m.group(2), text)
        if replaced != 1:
            raise ValueError(f'Expected one preload for {family}, got {replaced}')
    text = update_first_screen_hints(text)
    if text.count("ym(33578164, 'init'") != 1:
        raise ValueError('Metrika initialization changed')
    page.write_text(text)
    print(f'Updated {count} image tags, two font preloads and one stylesheet.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stylesheet', required=True)
    args = parser.parse_args()
    build(args.stylesheet)
