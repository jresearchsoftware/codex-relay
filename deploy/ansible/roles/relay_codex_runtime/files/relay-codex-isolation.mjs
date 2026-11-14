import { dirname } from 'node:path';
import { realpathSync } from 'node:fs';

// Imported only by the fixed root-owned launcher. Mount sources come from
// installed configuration and its validated checkout, never worker JSON.
export function isolatedCodexProcess({ binary, packageRoot, cwd, toolchainRoot, args }) {
  // The complete qualified distribution includes siblings of bin/codex.
  // Bind its fixed public payload root, not private installer/runtime homes
  // or the installation root containing registered runner credentials.
  const readonly = [...new Set(['/usr', '/bin', '/sbin', '/lib', '/lib64', dirname(binary), toolchainRoot, packageRoot])];
  const mounts = readonly.flatMap(root => ['--ro-bind-try', root, root]);
  // Debian tool aliases cross /etc/alternatives. Reconstruct only these public
  // command aliases to targets already present on the read-only OS mount.
  // Never expose the host alternatives directory or its unrelated targets.
  for (const name of ['cc', 'c++', 'awk']) {
    try {
      const target = realpathSync(`/usr/bin/${name}`);
      if (target.startsWith('/usr/')) mounts.push('--symlink', target, `/etc/alternatives/${name}`);
    } catch { /* An optional tool not installed on the host remains absent. */ }
  }
  for (const pathname of ['/etc/resolv.conf', '/etc/hosts', '/etc/nsswitch.conf', '/etc/passwd', '/etc/group',
    '/etc/ld.so.cache', '/etc/ssl/certs', '/etc/ca-certificates',
    // Preserve native administrator restrictions without exposing other /etc
    // configuration or private installation credentials to the worker.
    '/etc/codex/requirements.toml', '/etc/codex/managed_config.toml']) mounts.push('--ro-bind-try', pathname, pathname);
  return { command: '/usr/bin/bwrap', args: ['--die-with-parent', '--new-session', '--unshare-user', '--unshare-pid',
    '--unshare-ipc', '--unshare-uts', ...mounts, '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--tmpfs', '/run',
    '--bind', cwd, cwd, '--chdir', cwd, '--', binary, ...args] };
}
