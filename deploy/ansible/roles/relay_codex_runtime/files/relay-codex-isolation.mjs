import { dirname } from 'node:path';

// Imported only by the fixed root-owned launcher. Mount sources come from
// installed configuration and its validated checkout, never worker JSON.
export function isolatedCodexProcess({ binary, resolvedBinary, cwd, toolchainRoot, args }) {
  // Bind only CLI executable/package directories. The installation root also
  // contains registered runners and their credentials, which stay absent.
  const readonly = [...new Set(['/usr', '/bin', '/sbin', '/lib', '/lib64', dirname(binary), toolchainRoot, dirname(resolvedBinary)])];
  const mounts = readonly.flatMap(root => ['--ro-bind-try', root, root]);
  for (const pathname of ['/etc/resolv.conf', '/etc/hosts', '/etc/nsswitch.conf', '/etc/passwd', '/etc/group',
    '/etc/ld.so.cache', '/etc/ssl/certs', '/etc/ca-certificates']) mounts.push('--ro-bind-try', pathname, pathname);
  return { command: '/usr/bin/bwrap', args: ['--die-with-parent', '--new-session', '--unshare-user', '--unshare-pid',
    '--unshare-ipc', '--unshare-uts', ...mounts, '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--tmpfs', '/run',
    '--bind', cwd, cwd, '--chdir', cwd, '--', binary, ...args] };
}
