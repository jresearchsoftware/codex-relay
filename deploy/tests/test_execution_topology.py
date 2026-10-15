"""Numeric account aliases and ACL escapes cannot pass installed slot checks."""
import os
from pathlib import Path
import errno
import struct
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import execution_topology as topology
from test_execution_slots import inputs


def tables():
    config = inputs()
    names = [config['environment']['serviceUser'], config['environment']['reviewerUser'],
             config['environment']['runner']['user']]
    names += [slot[key] for slot in config['consumer']['executionSlots'] for key in ['runnerUser', 'runtimeUser']]
    users = [SimpleNamespace(pw_name=name, pw_uid=1000 + index, pw_gid=2000 + index)
             for index, name in enumerate(names)]
    groups = [SimpleNamespace(gr_name=user.pw_name, gr_gid=user.pw_gid, gr_mem=[])
              for user in users]
    groups += [SimpleNamespace(gr_name=slot['workGroup'], gr_gid=3000 + index,
                               gr_mem=[slot['runnerUser'], slot['runtimeUser']])
               for index, slot in enumerate(config['consumer']['executionSlots'])]
    return config, users, groups


def test_valid_topology_uses_real_numeric_separation_and_only_its_work_membership():
    config, users, groups = tables()
    resolved, _ = topology.identities(config, users, groups)
    assert len({resolved[name].pw_uid for name in resolved}) == len(users)


def test_fresh_numeric_preflight_allows_absent_accounts_without_creating_them():
    assert topology.numeric_preflight(inputs(), [], []) == {'existingUsers': 0, 'numericIdentity': 'distinct'}


def test_existing_foreign_numeric_alias_blocks_before_account_reconciliation():
    config, users, groups = tables()
    users.append(SimpleNamespace(pw_name='another-installation', pw_uid=users[-1].pw_uid, pw_gid=4000))
    with pytest.raises(ValueError, match='UID_ALIAS'):
        topology.numeric_preflight(config, users, groups)


@pytest.mark.parametrize('mutation', [
    lambda users, groups: setattr(users[-1], 'pw_uid', users[-2].pw_uid),
    lambda users, groups: users.append(SimpleNamespace(pw_name='foreign-alias', pw_uid=users[-1].pw_uid, pw_gid=4000)),
    lambda users, groups: setattr(groups[-1], 'gr_gid', groups[-2].gr_gid),
    lambda users, groups: groups.append(SimpleNamespace(gr_name='foreign-alias', gr_gid=groups[-1].gr_gid, gr_mem=[])),
    lambda users, groups: groups[-1].gr_mem.append(users[0].pw_name),
    lambda users, groups: groups[0].gr_mem.append(users[-1].pw_name),
    lambda users, groups: groups[-3].gr_mem.append(users[0].pw_name),
    lambda users, groups: setattr(users[-1], 'pw_uid', 0),
])
def test_numeric_aliases_foreign_members_and_extra_groups_fail_closed(mutation):
    config, users, groups = tables()
    mutation(users, groups)
    with pytest.raises(ValueError, match='EXECUTION_SLOT_'):
        topology.identities(config, users, groups)


@pytest.mark.parametrize('grant', ['user:9999:rwx', 'group:9999:r-x',
                                   'default:user:9999:rwx', 'other::r-x'])
def test_effective_or_inherited_foreign_acl_grants_cannot_open_slot_roots(grant):
    with pytest.raises(ValueError, match='FOREIGN_ACL'):
        topology.acl_safe('user::rwx\ngroup::rwx\nmask::rwx\nother::---\n' + grant,
                          {1000, 1001}, {2000})


def test_declared_numeric_acl_and_non_granting_entry_are_supported():
    topology.acl_safe('user::rwx\nuser:1001:rwx\nuser:9999:---\ngroup::rwx\n'
                      'default:group:2000:rwx\nmask::rwx\nother::---', {1000, 1001}, {2000})


@pytest.mark.skipif(sys.platform != 'linux', reason='native Linux POSIX ACL xattrs')
def test_native_default_acl_is_detected_without_reading_directory_contents(tmp_path):
    tmp_path.chmod(0o700)
    entries = [(1, 7, 0xffffffff), (2, 7, 65534), (4, 0, 0xffffffff),
               (16, 7, 0xffffffff), (32, 0, 0xffffffff)]
    binary = struct.pack('<I', 2) + b''.join(struct.pack('<HHI', *entry) for entry in entries)
    try:
        os.setxattr(tmp_path, 'system.posix_acl_default', binary, follow_symlinks=False)
    except OSError as error:
        if error.errno == errno.ENOTSUP:
            pytest.skip('fixture filesystem has no ACL support')
        raise
    raw = topology.native_acl(tmp_path)
    assert 'default:user:65534:rwx' in raw
    with pytest.raises(ValueError, match='FOREIGN_ACL'):
        topology.acl_safe(raw, {os.getuid()}, {os.getgid()})


def test_native_acl_absence_retains_the_ordinary_metadata_boundary(tmp_path):
    assert topology.native_acl(tmp_path) == ''
