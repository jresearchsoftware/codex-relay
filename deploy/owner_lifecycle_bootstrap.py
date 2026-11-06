"""Refresh only the fixed owner transport from freshly acquired accepted source.

This local root operation never installs product/runtime, touches admission or
changes service state. A later genuine owner dispatch still has to qualify the
entire bounded installer operation. Existing installed source stays immutable.
"""
import os
from pathlib import Path
import stat
import tempfile

import owner_lifecycle as owner
from config import compile_inputs
from deployment_lock import acquire
from installed_config import protected_parents, read_protected


TEMPLATE = 'deploy/ansible/roles/relay_runner/templates/relay-owner-lifecycle.j2'


def render(root, install, recovery_root=''):
    from jinja2 import Environment, StrictUndefined
    return Environment(undefined=StrictUndefined, keep_trailing_newline=True).from_string(
        (root / TEMPLATE).read_text()).render(relay_install_root=str(install),
            relay_owner_lifecycle_recovery_root=str(recovery_root)).encode()


def bootstrap(config, revision, *, filesystem_root=Path('/')):
    owner.require(os.geteuid() == 0, 'root-required')
    values = compile_inputs(config)
    install = Path(values['relay_install_root'])
    helper = Path(values['relay_owner_lifecycle_helper_path'])
    protected_parents(install / 'current')
    current = install / 'current'
    info = current.lstat()
    owner.require(stat.S_ISLNK(info.st_mode) and info.st_uid == 0, 'installed-current-binding')
    installed_source = Path(os.readlink(current)) / 'reviewed-source'
    installed = installed_source.parent.name
    with acquire(str(filesystem_root / 'var/lib' / (install.name + '-deployment.lock'))):
        actual_install, binding, _ = owner.git_anchor(installed, installed_source)
        owner.require(actual_install == install and config['environment']['localApply'] == {
            'source': 'git', 'repository': binding['repository'], 'configPath': binding['configPath']}
            and config['consumer']['owner'].casefold() == binding['owner'].casefold(),
            'bootstrap-installed-binding')
        repository = config['source']['repository'].removeprefix('https://github.com/').removeprefix(
            'git@github.com:').removesuffix('.git')
        owner.require(repository == binding['productRepository'] and owner.public_main(repository) == revision,
                      'bootstrap-accepted-main-required')
        # A fresh protected clone, never a runner/model-controlled Git checkout,
        # supplies every executed byte. No private-config credential is needed.
        stage = filesystem_root / 'var/lib' / install.name / 'owner-lifecycle-controllers'
        protected_parents(stage)
        if not stage.exists():
            stage.mkdir(mode=0o700)
        protected_parents(stage / 'entry')
        with tempfile.TemporaryDirectory(prefix='controller-', dir=stage) as temporary:
            selected = owner.acquire_source(Path(temporary) / 'source', repository, revision)
            owner.git_target_capability(selected)
            destination = stage / revision
            desired = render(selected, install, destination)
            previous, _ = read_protected(helper, {0o755}, group=0)
            original = render(installed_source, install)
            owner.require(previous in [original, desired], 'bootstrap-existing-helper-unrecognized')
            if destination.exists() or destination.is_symlink():
                # An interrupted bootstrap is observable, never overwritten.
                # Only an already published exact helper is idempotently reused.
                owner.require(previous == desired, 'bootstrap-stage-exists-inspect-before-retry')
                for name in ['owner_lifecycle.py', 'lifecycle.py', 'config.py', 'installed_config.py',
                             'deployment_lock.py', 'git_intent.py', 'repository_source.py']:
                    raw, _ = read_protected(destination / 'deploy' / name, {0o644, 0o755, 0o600, 0o700}, group=0)
                    owner.require(raw == (selected / 'deploy' / name).read_bytes(), 'bootstrap-controller-drift')
                return revision
            for path in [selected, *selected.rglob('*')]:
                metadata = path.lstat()
                owner.require(metadata.st_uid == 0 and (stat.S_ISDIR(metadata.st_mode)
                    or stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1), 'bootstrap-source-unsafe')
                path.chmod(stat.S_IMODE(metadata.st_mode) & ~0o022)
            os.rename(selected, destination)
            directory = os.open(stage, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            # The operation reserves the new immutable controller before helper
            # publication. An interrupted publication keeps it for diagnosis.
            fd, temporary_helper = tempfile.mkstemp(prefix=helper.name + '.', dir=helper.parent)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(desired)
                    stream.flush()
                    os.fchmod(stream.fileno(), 0o755)
                    os.fsync(stream.fileno())
                owner.git_anchor(installed, installed_source)
                owner.require(read_protected(helper, {0o755}, group=0)[0] == previous,
                              'bootstrap-helper-changed')
                os.replace(temporary_helper, helper)
                directory = os.open(helper.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                if os.path.exists(temporary_helper):
                    os.unlink(temporary_helper)
            owner.require(read_protected(helper, {0o755}, group=0)[0] == desired, 'bootstrap-readback-failed')
            return revision
