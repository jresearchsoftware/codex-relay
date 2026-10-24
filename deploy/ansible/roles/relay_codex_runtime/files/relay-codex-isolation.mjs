import { dirname } from 'node:path';

// Imported only by the fixed root-owned launcher. Mount sources come from
// installed configuration and its validated checkout, never worker JSON.
export function isolatedCodexProcess({ binary, packageRoot, cwd, toolchainRoot, args }) {
  // The complete qualified distribution includes siblings of bin/codex.
  // Bind its fixed public payload root, not private installer/runtime homes
  // or the installation root containing registered runner credentials.
  const readonly = [...new Set(['/usr', '/bin', '/sbin', '/lib', '/lib64', dirname(binary), toolchainRoot, packageRoot])];
  const mounts = readonly.flatMap(root => ['--ro-bind-try', root, root]);
  for (const pathname of ['/etc/resolv.conf', '/etc/hosts', '/etc/nsswitch.conf', '/etc/passwd', '/etc/group',
    '/etc/ld.so.cache', '/etc/ssl/certs', '/etc/ca-certificates',
    // Preserve native administrator restrictions without exposing other /etc
    // configuration or private installation credentials to the worker.
    '/etc/codex/requirements.toml', '/etc/codex/managed_config.toml']) mounts.push('--ro-bind-try', pathname, pathname);
  return { command: '/usr/bin/bwrap', args: ['--die-with-parent', '--new-session', '--unshare-user', '--unshare-pid',
    '--unshare-ipc', '--unshare-uts', ...mounts, '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--tmpfs', '/run',
    '--bind', cwd, cwd, '--chdir', cwd, '--', binary, ...args] };
}
