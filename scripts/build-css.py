#!/usr/bin/env python3
"""Build the complete stylesheet without changing the accepted cascade.

Build dependencies (not needed by the deployed website):
    python3 -m pip install tinycss2==1.4.0 rcssmin==1.2.1
Run from any directory:
    python3 scripts/build-css.py

Run the image/font build first. Original editable stylesheets and assets remain
in the repository. The manifest resolves their URLs to immutable built assets.
"""

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import posixpath
from urllib.parse import urlsplit

import rcssmin
import tinycss2
from tinycss2.ast import StringToken, URLToken


ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    "reset.css",
    "variables.css",
    "style.css",
    "responsive.css",
    "contacts.css",
    "harmony.css",
    "performance.css",
)


def url_map_from_manifest(manifest):
    result = {}
    for original_url, entry in manifest["images"].items():
        variants = entry["variants"]
        if not variants:
            raise ValueError(f"Missing image variants: {original_url}")
        # CSS paper textures can span several differently sized compositions.
        # Use the largest built variant to preserve their texture everywhere.
        # The HTML image build uses responsive sizes independently.
        result[original_url] = max(variants, key=lambda item: item["width"])["src"]
    for family, source in (("Inter", "inter-variable.woff2"),
                           ("Caveat", "caveat-variable.woff2")):
        result[f"/assets/fonts/{source}"] = manifest["fonts"][family]["src"]
    return result


def rewrite_urls(tokens, source_url, url_map):
    """Rewrite parsed URL tokens, including quoted URLs inside nested rules."""
    for index, token in enumerate(tokens):
        value = None
        if token.type == "url":
            value = token.value
        elif token.type == "function" and token.lower_name == "url":
            arguments = [item for item in token.arguments
                         if item.type not in ("whitespace", "comment")]
            if len(arguments) == 1 and arguments[0].type == "string":
                value = arguments[0].value
            else:
                raise ValueError(f"Unsupported CSS url(): {tinycss2.serialize([token])}")

        if value is not None:
            parsed = urlsplit(value)
            if not parsed.scheme and not parsed.netloc and not value.startswith("#"):
                absolute_url = posixpath.normpath(posixpath.join(
                    posixpath.dirname(source_url), parsed.path))
                replacement = url_map.get(absolute_url, absolute_url)
                replacement_path = ROOT / urlsplit(replacement).path.lstrip("/")
                if not replacement_path.is_file():
                    raise FileNotFoundError(f"CSS asset missing: {replacement}")
                # Generated root-relative paths contain no query strings.
                if parsed.query:
                    replacement += "?" + parsed.query
                if parsed.fragment:
                    replacement += "#" + parsed.fragment
                if token.type == "url":
                    tokens[index] = URLToken(token.source_line, token.source_column,
                                             replacement, f"url({replacement})")
                else:
                    token.arguments = [StringToken(
                        token.source_line, token.source_column, replacement,
                        json.dumps(replacement))]
        else:
            for attribute in ("content", "arguments", "prelude"):
                children = getattr(token, attribute, None)
                if children is not None:
                    rewrite_urls(children, source_url, url_map)


def ensure_valid(tokens, label):
    for token in tokens:
        if token.type == "error":
            raise ValueError(f"Invalid CSS in {label}: {token.message}")
        for attribute in ("content", "arguments", "prelude"):
            children = getattr(token, attribute, None)
            if children is not None:
                ensure_valid(children, label)


def expand_font_faces(rules, manifest):
    """Keep a complete face available behind a smaller unicode-scoped face.

    The later core face handles its declared characters. Other characters can
    load the full subset on demand without making ordinary page visits fetch
    both files. Preserve the original style, weight range and font-display.
    """
    expanded = []
    for rule in rules:
        if rule.type != "at-rule" or rule.lower_at_keyword != "font-face":
            expanded.append(rule)
            continue
        declarations = tinycss2.parse_declaration_list(rule.content)
        family = next((tinycss2.serialize(item.value).strip().strip("\"'")
                       for item in declarations
                       if item.type == "declaration" and item.lower_name == "font-family"), None)
        font = manifest["fonts"].get(family, {})
        if not font.get("fallbackSrc"):
            expanded.append(rule)
            continue
        if not isinstance(font.get("unicodeRange"), str) or not font["unicodeRange"]:
            raise ValueError(f"Core font needs a CSS unicodeRange: {family}")
        fallback = copy.deepcopy(rule)
        fallback_declarations = tinycss2.parse_declaration_list(fallback.content)
        for declaration in fallback_declarations:
            if declaration.type == "declaration" and declaration.lower_name == "src":
                declaration.value = tinycss2.parse_component_value_list(
                    f"url({json.dumps(font['fallbackSrc'])}) format('woff2')")
        fallback.content = tinycss2.parse_component_value_list(
            tinycss2.serialize(fallback_declarations))
        # The editable source currently has no unicode-range. Reject an
        # ambiguous source definition rather than silently overriding it.
        if any(item.type == "declaration" and item.lower_name == "unicode-range"
               for item in declarations):
            raise ValueError(f"Source font already has unicode-range: {family}")
        rule.content.extend(tinycss2.parse_component_value_list(
            f";unicode-range:{font['unicodeRange']};"))
        expanded.extend((fallback, rule))
    return expanded


def build(manifest_path):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    url_map = url_map_from_manifest(manifest)
    chunks = []
    source_bytes = 0
    for filename in SOURCES:
        source = ROOT / "assets/css" / filename
        text = source.read_text(encoding="utf-8")
        source_bytes += len(text.encode("utf-8"))
        parsed = tinycss2.parse_stylesheet(text, skip_comments=True)
        ensure_valid(parsed, filename)
        parsed = expand_font_faces(parsed, manifest)
        rewrite_urls(parsed, f"/assets/css/{filename}", url_map)
        chunks.append(tinycss2.serialize(parsed))

    # Only lexical minification; do not merge/reorder selectors, remove rules,
    # alter specificity or move media queries between the source layers.
    minified = rcssmin.cssmin("\n".join(chunks)).encode("utf-8")
    ensure_valid(tinycss2.parse_stylesheet(minified.decode("utf-8")), "bundle")
    digest = hashlib.sha256(minified).hexdigest()[:12]
    output = ROOT / "assets/optimized" / f"site-{digest}.css"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(minified)
    compressed = gzip.compress(minified, compresslevel=9, mtime=0)
    output.with_suffix(".css.gz").write_bytes(compressed)
    print(json.dumps({
        "stylesheet": "/" + output.relative_to(ROOT).as_posix(),
        "sourceBytes": source_bytes,
        "bytes": len(minified),
        "gzipBytes": len(compressed),
        "sha256": hashlib.sha256(minified).hexdigest(),
    }, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path,
                        default=ROOT / "assets/optimized/manifest.json")
    arguments = parser.parse_args()
    build(arguments.manifest)
