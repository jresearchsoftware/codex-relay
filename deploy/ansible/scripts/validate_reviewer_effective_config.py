"""Validate the structural nginx configuration emitted by ``nginx -T``.

The input is nginx's include-expanded, parsed configuration dump. This
validator tokenizes nginx syntax instead of assigning meaning to physical
lines, and emits only bounded cardinality evidence.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import sys


@dataclass
class Block:
    header: list[str] = field(default_factory=list)
    directives: list[list[str]] = field(default_factory=list)
    children: list["Block"] = field(default_factory=list)


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    quote = ""
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if quote:
            if escaped:
                current.append(char)
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            else:
                current.append(char)
        elif char in "'\"":
            quote = char
        elif char == "#":
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue
        elif char.isspace():
            if current:
                tokens.append("".join(current))
                current = []
        elif char in "{};":
            if current:
                tokens.append("".join(current))
                current = []
            tokens.append(char)
        else:
            current.append(char)
        index += 1
    if quote or escaped:
        raise ValueError("unterminated nginx token")
    if current:
        tokens.append("".join(current))
    return tokens


def parse(text: str) -> Block:
    root = Block()
    stack = [root]
    pending: list[str] = []
    for token in tokenize(text):
        if token == ";":
            if not pending:
                raise ValueError("empty nginx directive")
            stack[-1].directives.append(pending)
            pending = []
        elif token == "{":
            if not pending:
                raise ValueError("empty nginx block")
            child = Block(header=pending)
            stack[-1].children.append(child)
            stack.append(child)
            pending = []
        elif token == "}":
            if pending or len(stack) == 1:
                raise ValueError("invalid nginx block closure")
            stack.pop()
        else:
            pending.append(token)
    if pending or len(stack) != 1:
        raise ValueError("unterminated nginx configuration")
    return root


def descendants(block: Block):
    for child in block.children:
        yield child
        yield from descendants(child)


def direct_directives(block: Block, name: str) -> list[list[str]]:
    return [directive for directive in block.directives if directive and directive[0] == name]


def hostname_equal(left: str, right: str) -> bool:
    return left.rstrip(".").casefold() == right.rstrip(".").casefold()


def listens_on_https(block: Block) -> bool:
    for directive in direct_directives(block, "listen"):
        if len(directive) < 2:
            continue
        endpoint = directive[1].casefold()
        if endpoint == "443" or endpoint.endswith(":443"):
            return True
    return False


def hostname_candidate(name: str, host: str) -> bool:
    name = name.rstrip(".").casefold()
    host = host.rstrip(".").casefold()
    if hostname_equal(name, host):
        return True
    if name.startswith("*."):
        suffix = name[1:]
        return host.endswith(suffix) and host != suffix[1:]
    if name.startswith("."):
        suffix = name.casefold()
        return host.endswith(suffix) or host == suffix[1:]
    if name.endswith(".*") and name.count("*") == 1:
        prefix = name[:-2]
        return host.startswith(prefix + ".") and len(host) > len(prefix) + 1
    return False


def server_names(block: Block) -> list[str]:
    return [name for directive in direct_directives(block, "server_name") for name in directive[1:]]


def validate(
    text: str,
    host: str,
    expected_claims: int | None,
    expected_proxy_pass: str | None,
    allowed_claims: set[int] | None = None,
    require_relay_marker: bool = False,
) -> tuple[int, int, int]:
    if require_relay_marker and "# managed-by: codex-relay-docker-nginx" not in text.splitlines():
        raise ValueError("RELAY_FRAGMENT_MARKER_MISSING")
    root = parse(text)
    servers = [
        block for block in descendants(root)
        if block.header and block.header[0] == "server" and listens_on_https(block)
    ]
    for block in servers:
        if any(name.startswith("~") for name in server_names(block)):
            raise ValueError("AMBIGUOUS_REGEX_SERVER_NAME")
    claiming_servers = [
        block for block in servers
        if any(hostname_candidate(name, host) for name in server_names(block))
    ]
    exact_servers = [
        block for block in servers
        if any(hostname_equal(name, host) for name in server_names(block))
    ]
    claims = len(claiming_servers)
    if allowed_claims is not None:
        if claims not in allowed_claims:
            raise ValueError(f"HOSTNAME_CANDIDATES={claims};allowed={sorted(allowed_claims)}")
    elif claims != expected_claims:
        raise ValueError(f"HOSTNAME_CANDIDATES={claims};expected={expected_claims}")
    if expected_proxy_pass is None and claims == 0:
        return claims, 0, 0

    if claims != 1 or len(exact_servers) != 1:
        raise ValueError("REVIEWER_SERVER_CARDINALITY_INVALID")
    reviewer = exact_servers[0]
    locations = [block for block in descendants(reviewer) if block.header == ["location", "=", "/mcp"]]
    if len(locations) != 1:
        raise ValueError(f"MCP_LOCATION_CARDINALITY={len(locations)};expected=1")
    proxies = direct_directives(locations[0], "proxy_pass")
    if expected_proxy_pass is None:
        if len(proxies) != 1:
            raise ValueError(f"MCP_PROXY_CARDINALITY={len(proxies)};expected=1")
        return claims, len(locations), 1
    expected = expected_proxy_pass.rstrip(";")
    matching = sum(
        1 for directive in proxies
        if len(directive) == 2 and directive[1].rstrip(";") == expected
    )
    if len(proxies) != 1 or matching != 1:
        raise ValueError(f"MCP_PROXY_CARDINALITY={len(proxies)};matching={matching};expected=1")
    return claims, len(locations), matching


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--expected-claims", required=True, type=int)
    parser.add_argument(
        "--allowed-claims",
        help="Comma-separated claim cardinalities admitted for replacement preflight",
    )
    parser.add_argument("--require-relay-marker", action="store_true")
    parser.add_argument("--expected-proxy-pass")
    args = parser.parse_args()
    try:
        allowed_claims = (
            {int(value) for value in args.allowed_claims.split(",")}
            if args.allowed_claims
            else None
        )
        claims, locations, proxies = validate(
            sys.stdin.read(),
            args.host,
            args.expected_claims,
            args.expected_proxy_pass,
            allowed_claims,
            args.require_relay_marker,
        )
    except (ValueError, UnicodeError) as error:
        print(f"REVIEWER_EFFECTIVE_CONFIG_INVALID={error}", file=sys.stderr)
        return 1
    print(
        "REVIEWER_EFFECTIVE_CONFIG=STRUCTURAL;"
        f"claims={claims};mcp_locations={locations};matching_proxies={proxies}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
