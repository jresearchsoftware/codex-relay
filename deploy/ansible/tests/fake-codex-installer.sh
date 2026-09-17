#!/bin/sh
# Only the external Codex distribution is substituted. Keep the official
# installer's mkdir/symlink topology and inherited deploy umask: root install
# under UMask=0077 creates the package ancestors and release root as 0700.
set -eu
test "$1" = --release
test "$2" = 0.154.0
release="$CODEX_HOME/packages/standalone/releases/$2-x86_64-unknown-linux-musl"
mkdir -p "$release" "$CODEX_INSTALL_DIR"
# These descendants come from the official tar archive with preserved modes.
mkdir -p "$release/bin"
chmod 0755 "$release/bin"
cp /run/fake-installed-codex.mjs "$release/bin/codex"
cp /run/rust-development-probe.mjs "$release/bin/rust-development-probe.mjs"
chmod 0644 "$release/bin/rust-development-probe.mjs"
chmod 0755 "$release/bin/codex"
chown 1001:1001 "$release/bin" "$release/bin/codex"
ln -s "$release" "$CODEX_HOME/packages/standalone/current"
ln -s "$CODEX_HOME/packages/standalone/current/bin/codex" "$CODEX_INSTALL_DIR/codex"
printf 'Codex CLI 0.154.0 installed (disposable substitute)\n'
