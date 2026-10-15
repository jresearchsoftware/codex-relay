"""Read-only numeric identity and access-boundary proof for installed slots."""
import grp
import errno
import json
import os
from pathlib import Path
import pwd
import stat
import struct
import sys


def require(value, code):
    if not value:
        raise ValueError('EXECUTION_SLOT_' + code)


def numeric_preflight(config, accounts=None, groups=None):
    """Check existing NSS aliases before creating or reconciling slot accounts."""
    accounts = list(pwd.getpwall() if accounts is None else accounts)
    groups = list(grp.getgrall() if groups is None else groups)
    slots = config['consumer']['executionSlots']
    protected = [config['environment'][key] for key in ['serviceUser', 'reviewerUser']]
    protected.append(config['environment']['runner']['user'])
    names = protected + [slot[key] for slot in slots for key in ['runnerUser', 'runtimeUser']]
    users = [entry for entry in accounts if entry.pw_name in names]
    require(all(entry.pw_uid != 0 and entry.pw_gid != 0 for entry in users), 'ROOT_IDENTITY')
    for entry in users:
        require([other.pw_name for other in accounts if other.pw_uid == entry.pw_uid] == [entry.pw_name], 'UID_ALIAS')
    slot_group_names = [slot[key] for slot in slots for key in ['runnerUser', 'runtimeUser', 'workGroup']]
    existing_groups = [entry for entry in groups if entry.gr_name in slot_group_names]
    protected_gids = {entry.pw_gid for entry in users if entry.pw_name in protected}
    for entry in existing_groups:
        require(entry.gr_gid != 0 and entry.gr_gid not in protected_gids, 'GID_ALIAS')
        require([other.gr_name for other in groups if other.gr_gid == entry.gr_gid] == [entry.gr_name], 'GID_ALIAS')
    return {'existingUsers': len(users), 'numericIdentity': 'distinct'}


def identities(config, accounts=None, groups=None):
    """Names alone do not prove separation: inspect UID/GID aliases and members."""
    live = accounts is None and groups is None
    accounts = list(pwd.getpwall() if accounts is None else accounts)
    groups = list(grp.getgrall() if groups is None else groups)
    numeric_preflight(config, accounts, groups)
    by_user = {entry.pw_name: entry for entry in accounts}
    by_group = {entry.gr_name: entry for entry in groups}
    memberships = {entry.pw_name: (set(os.getgrouplist(entry.pw_name, entry.pw_gid)) if live else
                   {entry.pw_gid} | {group.gr_gid for group in groups if entry.pw_name in group.gr_mem})
                   for entry in accounts}
    slots = config['consumer']['executionSlots']
    protected = [config['environment'][key] for key in ['serviceUser', 'reviewerUser']]
    protected.append(config['environment']['runner']['user'])
    names = protected + [slot[key] for slot in slots for key in ['runnerUser', 'runtimeUser']]
    require(all(name in by_user for name in names), 'IDENTITY_MISSING')
    users = [by_user[name] for name in names]
    require(all(entry.pw_uid != 0 and entry.pw_gid != 0 for entry in users), 'ROOT_IDENTITY')
    require(len({entry.pw_uid for entry in users}) == len(users), 'UID_ALIAS')
    for entry in users:
        require([other.pw_name for other in accounts if other.pw_uid == entry.pw_uid] == [entry.pw_name], 'UID_ALIAS')
    slot_groups = [slot[key] for slot in slots for key in ['runnerUser', 'runtimeUser', 'workGroup']]
    require(all(name in by_group for name in slot_groups), 'GROUP_MISSING')
    gids = [by_group[name].gr_gid for name in slot_groups]
    require(0 not in gids and len(set(gids)) == len(gids)
            and not set(gids) & {by_user[name].pw_gid for name in protected}, 'GID_ALIAS')
    for name in slot_groups:
        entry = by_group[name]
        require([other.gr_name for other in groups if other.gr_gid == entry.gr_gid] == [name], 'GID_ALIAS')
    for slot in slots:
        allowed = {slot['runnerUser'], slot['runtimeUser']}
        work_gid = by_group[slot['workGroup']].gr_gid
        members = {entry.pw_name for entry in accounts if work_gid in memberships[entry.pw_name]}
        members.update(by_group[slot['workGroup']].gr_mem)
        # getgrouplist includes NSS supplementary memberships absent from group
        # enumeration. Fixture tables use the equivalent explicit members.
        require(members <= allowed, 'FOREIGN_WORK_MEMBER')
        for name in allowed:
            entry = by_user[name]
            require(entry.pw_gid == by_group[name].gr_gid, 'PRIMARY_GROUP')
            require(memberships[name] == {entry.pw_gid, work_gid}, 'SUPPLEMENTARY_GROUP')
            private_members = {other.pw_name for other in accounts if entry.pw_gid in memberships[other.pw_name]}
            private_members.update(by_group[name].gr_mem)
            require(private_members == {name}, 'FOREIGN_PRIVATE_MEMBER')
    return by_user, by_group


def acl_safe(raw, allowed_users, allowed_groups):
    """Reject effective named/default ACL grants beyond the declared boundary."""
    for line in raw.splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        if line.startswith('default:'):
            line = line[len('default:'):]
        fields = line.split(':')
        require(len(fields) == 3 and fields[0] in ['user', 'group', 'mask', 'other'], 'ACL_UNPROVEN')
        kind, principal, rights = fields
        require(len(rights) == 3 and all(c in 'rwx-' for c in rights), 'ACL_UNPROVEN')
        if kind == 'other':
            require(rights == '---', 'FOREIGN_ACL')
        elif principal and rights != '---':
            require(principal.isdecimal() and int(principal) in (
                allowed_users if kind == 'user' else allowed_groups), 'FOREIGN_ACL')


def native_acl(path):
    """Read Linux POSIX ACL metadata without adding an operator dependency.

    Linux UAPI posix_acl_xattr.h defines version 2, a little-endian u32 header
    and u16 tag/u16 permissions/u32 id entries. Missing xattrs have no named
    grants; the caller separately verifies ordinary mode/owner/group access.
    """
    tags = {1: ('user', False), 2: ('user', True), 4: ('group', False),
            8: ('group', True), 16: ('mask', False), 32: ('other', False)}
    lines = []
    for name, prefix in [('system.posix_acl_access', ''), ('system.posix_acl_default', 'default:')]:
        try:
            raw = os.getxattr(path, name, follow_symlinks=False)
        except OSError as error:
            if error.errno in [errno.ENODATA, errno.ENOTSUP]:
                continue
            raise
        require(4 <= len(raw) <= 65536 and (len(raw) - 4) % 8 == 0
                and struct.unpack_from('<I', raw)[0] == 2, 'ACL_UNPROVEN')
        for offset in range(4, len(raw), 8):
            tag, permissions, identity = struct.unpack_from('<HHI', raw, offset)
            require(tag in tags and permissions <= 7, 'ACL_UNPROVEN')
            kind, named = tags[tag]
            require((identity != 0xffffffff) == named, 'ACL_UNPROVEN')
            rights = ''.join(character if permissions & bit else '-'
                             for character, bit in [('r', 4), ('w', 2), ('x', 1)])
            lines.append(prefix + kind + ':' + (str(identity) if named else '') + ':' + rights)
    return '\n'.join(lines)


def inspect(config, *, root=Path('/'), accounts=None, groups=None, owner_uid=0, acl_reader=None):
    by_user, by_group = identities(config, accounts, groups)
    namespace = config['environment']['namespace']
    for slot in config['consumer']['executionSlots']:
        runner, runtime = by_user[slot['runnerUser']], by_user[slot['runtimeUser']]
        work_gid = by_group[slot['workGroup']].gr_gid
        credential = '/etc/' + namespace + ('' if slot['id'] == 'primary' else '/slots/' + slot['id']) + '/codex-credentials'
        runner_root = '/opt/' + namespace + ('/general-runner' if slot['id'] == 'primary' else '/slots/' + slot['id'] + '/runner')
        roots = [(slot['paths']['workRoot'], runner.pw_uid, work_gid, 0o2770, {runner.pw_uid, runtime.pw_uid}, {work_gid}),
                 (str(Path(slot['paths']['attemptRoot']).parent), runner.pw_uid, runner.pw_gid, 0o700, {runner.pw_uid}, {runner.pw_gid}),
                 (credential, runtime.pw_uid, runtime.pw_gid, 0o700, {runtime.pw_uid}, {runtime.pw_gid}),
                 (runner_root, runner.pw_uid, runner.pw_gid, 0o750, {runner.pw_uid}, {runner.pw_gid}),
                 (slot['paths']['diagnosticsRoot'], owner_uid, 0 if owner_uid == 0 else os.getgid(), 0o700, {owner_uid}, {0})]
        for logical, uid, gid, mode, users, gids in roots:
            path = root / logical.lstrip('/')
            info = path.lstat()
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == uid and info.st_gid == gid
                    and stat.S_IMODE(info.st_mode) == mode, 'ROOT_METADATA')
            # Root-controlled namespace ancestors prevent replacement between
            # the metadata check and use. No worker-controlled symlink is read.
            for ancestor in path.parents:
                if ancestor == root:
                    break
                metadata = ancestor.lstat()
                require(stat.S_ISDIR(metadata.st_mode) and metadata.st_uid == owner_uid
                        and not metadata.st_mode & 0o022, 'PARENT_UNSAFE')
            raw = acl_reader(path) if acl_reader else native_acl(path)
            acl_safe(raw, users | {owner_uid}, gids | {0})
    return {'slots': len(config['consumer']['executionSlots']), 'numericIdentity': 'distinct', 'access': 'isolated'}


if __name__ == '__main__':
    try:
        config = json.loads(sys.stdin.read())
        result = numeric_preflight(config) if sys.argv[1:] == ['--identities'] else inspect(config)
        require(sys.argv[1:] in [[], ['--identities']], 'ARGUMENTS')
        print('EXECUTION_SLOT_TOPOLOGY=' + json.dumps(result, sort_keys=True))
    except (ValueError, KeyError, OSError):
        print('EXECUTION_SLOT_TOPOLOGY_UNPROVEN', file=sys.stderr)
        raise SystemExit(1)
