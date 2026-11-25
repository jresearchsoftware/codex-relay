"""Bounded public timing grammar shared by backend and owner forwarding."""
import re

UUID = r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}'
NUMBER = r'[0-9]{1,12}'
ROLE = r'(?:relay_[a-z_]{1,60}|playbook|other|redacted)'
TASK = r'(?:[0-9a-f]{12}|redacted|unavailable)'
PREFIX = r'RELAY_ANSIBLE_TIMING=operation=('
PATTERN = re.compile(PREFIX + UUID + r');invocation=(' + UUID + r');(?:'
    + rf'kind=task;task={TASK};role={ROLE};state=(?:ok|failed|skipped|unreachable);start_ms={NUMBER};end_ms={NUMBER};wall_ms={NUMBER}'
    + rf'|kind=backend;wall_ms={NUMBER}'
    + rf'|kind=role;role={ROLE};tasks={NUMBER};start_ms={NUMBER};end_ms={NUMBER};wall_ms={NUMBER}'
    + rf'|kind=summary;wall_ms={NUMBER};observed_union_ms={NUMBER};gap_ms={NUMBER};unfinished={NUMBER};overlap=possible)')


def public_ansible_timing(line, operation=None, invocation=None):
    """Accept the whole fixed record, never a substring of private output."""
    match = PATTERN.fullmatch(line)
    return bool(match and (operation is None or match[1] == operation)
                and (invocation is None or match[2] == invocation))


def main():
    """Resolve an opaque task ID locally against the exact observed source."""
    import argparse
    from hashlib import sha256
    from pathlib import Path
    parser = argparse.ArgumentParser(description='Resolve a public task timing ID against this exact source checkout')
    parser.add_argument('--resolve-task', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{12}', args.resolve_task):
        parser.error('expected a 12-hex source task identifier')
    root = Path(__file__).resolve().parent / 'ansible'
    for path in sorted(root.rglob('*.yml')):
        relative = path.relative_to(root).as_posix()
        for line in range(1, len(path.read_bytes().splitlines()) + 1):
            key = sha256(f'{relative}:{line}'.encode()).hexdigest()[:12]
            if key == args.resolve_task:
                print(f'{path}:{line}')
                return
    parser.exit(1, 'Task identifier unavailable in this checkout; use the exact observed product revision.\n')


if __name__ == '__main__':
    main()
