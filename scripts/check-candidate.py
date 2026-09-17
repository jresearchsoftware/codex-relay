#!/usr/bin/env python3
"""Check tracked candidate JSON, local Markdown links and credential markers.

Reports paths/line numbers only, never matching secret bytes. This is a bounded
source check, not a substitute for independent security or deployment review.
"""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_EXTRA_MARKERS = re.compile(rb'(?:AKIA[0-9A-Z]{16}|sk-(?:proj-)?[A-Za-z0-9_-]{40,})')


def anchors(text):
    result, counts = set(), {}
    for title in re.findall(r'^#{1,6}\s+(.+?)\s*#*$', text, re.M):
        name = re.sub(r'[^\w\- ]', '', title.lower()).replace(' ', '-')
        count = counts.get(name, 0)
        counts[name] = count + 1
        result.add(f'{name}-{count}' if count else name)
    return result


def main():
    files = [Path(p) for p in subprocess.check_output(
        ['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0') if p]
    spec = importlib.util.spec_from_file_location('secret_scan', ROOT / 'contracts/src/secret-scan.py')
    scanner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scanner)
    failures, links = [], 0
    for relative in files:
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            failures.append(f'{relative}: missing or non-regular candidate file')
            continue
        data = path.read_bytes()
        if scanner.MARKER.search(data) or CANDIDATE_EXTRA_MARKERS.search(data):
            failures.append(f'{relative}: credential marker')
        text = data.decode('utf-8')
        if path.suffix == '.json':
            try:
                json.loads(text)
            except ValueError:
                failures.append(f'{relative}: invalid JSON')
        if path.suffix != '.md':
            continue
        # Fenced examples may contain intentionally invalid Markdown/URLs.
        prose = re.sub(r'^```[^\n]*\n.*?^```\s*$', '', text, flags=re.M | re.S)
        for match in re.finditer(r'\[[^\]\n]*\]\(([^)\s]+)\)', prose):
            url = urlsplit(match.group(1).strip('<>'))
            if url.scheme or url.netloc:
                continue
            links += 1
            target = (path.parent / unquote(url.path)).resolve() if url.path else path.resolve()
            valid = target.is_relative_to(ROOT) and target.exists()
            if valid and url.fragment and target.suffix == '.md':
                valid = unquote(url.fragment) in anchors(target.read_text(encoding='utf-8'))
            if not valid:
                failures.append(f'{relative}: broken local link {match.group(1)}')
    for failure in failures:
        print(failure)
    print(json.dumps({'candidate': 'FAIL' if failures else 'PASS',
                      'trackedFiles': len(files), 'localLinks': links,
                      'scope': 'JSON syntax, local Markdown links, bounded credential markers'}))
    return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
