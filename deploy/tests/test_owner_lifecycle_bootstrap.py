"""Exercise the separate fixed-helper bootstrap in an isolated Linux root tree."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import owner_lifecycle_bootstrap as bootstrap


REPO = Path(__file__).resolve().parents[2]
HEAD, OLD = 'a' * 40, 'b' * 40


def test_render_preserves_regular_route_and_limits_bootstrap_to_recover():
    normal = bootstrap.render(REPO, Path('/opt/example')).decode()
    recovered = bootstrap.render(REPO, Path('/opt/example'), '/var/lib/example/controllers/' + HEAD).decode()
    assert '--installed-source' not in normal
    assert 'if [[ "$1" == git:recover:* ]]' in recovered
    assert '--installed-source "$PRODUCT_ROOT"' in recovered
    assert 'root = release /' in recovered
    for content in [normal, recovered]:
        assert subprocess.run(['/bin/bash', '-n'], input=content, text=True).returncode == 0


@pytest.fixture
def protected_root():
    if os.geteuid() != 0:
        pytest.skip('native root protected-filesystem proof')
    with tempfile.TemporaryDirectory(prefix='relay-owner-bootstrap-', dir='/run') as directory:
        yield Path(directory)


def test_bootstrap_only_refreshes_transport_and_rejects_drift(protected_root):
    root = protected_root
    install = root / 'opt/fixture'
    installed_source = install / 'releases' / OLD / 'reviewed-source'
    installed_source.mkdir(parents=True)
    (root / 'var/lib/fixture').mkdir(parents=True)
    helper = root / 'usr/local/sbin/fixture-owner-lifecycle'
    helper.parent.mkdir(parents=True)
    (install / 'current').symlink_to(installed_source.parent)
    template = installed_source / bootstrap.TEMPLATE
    template.parent.mkdir(parents=True)
    template.write_bytes((REPO / bootstrap.TEMPLATE).read_bytes())
    helper.write_bytes(bootstrap.render(installed_source, install))
    helper.chmod(0o755)
    config = {'source': {'repository': 'https://github.com/example/product'}, 'consumer': {'owner': 'owner'},
              'environment': {'localApply': {'source': 'git', 'repository': 'example/config', 'configPath': 'prod.json'}}}
    binding = {'productRepository': 'example/product', 'repository': 'example/config',
               'configPath': 'prod.json', 'owner': 'owner'}
    values = {'relay_install_root': str(install), 'relay_owner_lifecycle_helper_path': str(helper)}
    anchors, fetches = [], []

    def anchor(*args):
        anchors.append(args)
        return install, binding, {}

    def fetch(directory, repository, revision):
        fetches.append((repository, revision))
        (directory / 'deploy').mkdir(parents=True)
        for name in ['owner_lifecycle.py', 'lifecycle.py', 'config.py', 'installed_config.py',
                     'deployment_lock.py', 'git_intent.py', 'repository_source.py', 'installation-contract.json']:
            shutil.copyfile(REPO / 'deploy' / name, directory / 'deploy' / name)
        target = directory / bootstrap.TEMPLATE
        target.parent.mkdir(parents=True)
        shutil.copyfile(REPO / bootstrap.TEMPLATE, target)
        return directory

    before = (install / 'current').readlink()
    with patch.object(bootstrap, 'compile_inputs', return_value=values), \
         patch.object(bootstrap.owner, 'git_anchor', side_effect=anchor), \
         patch.object(bootstrap.owner, 'public_main', return_value=HEAD), \
         patch.object(bootstrap.owner, 'acquire_source', side_effect=fetch):
        assert bootstrap.bootstrap(config, HEAD, filesystem_root=root) == HEAD
        final = helper.read_bytes()
        assert (install / 'current').readlink() == before
        controller = root / 'var/lib/fixture/owner-lifecycle-controllers' / HEAD
        assert final == bootstrap.render(controller, install, controller)
        assert bootstrap.bootstrap(config, HEAD, filesystem_root=root) == HEAD
        assert helper.read_bytes() == final
        assert len(fetches) == 2
        (controller / 'deploy/owner_lifecycle.py').write_text('# modified\n')
        with pytest.raises(ValueError, match='bootstrap-controller-drift'):
            bootstrap.bootstrap(config, HEAD, filesystem_root=root)
        assert helper.read_bytes() == final
        with patch.object(bootstrap.owner, 'public_main', return_value=OLD):
            with pytest.raises(ValueError, match='bootstrap-accepted-main-required'):
                bootstrap.bootstrap(config, HEAD, filesystem_root=root)
        helper.unlink()
        helper.symlink_to(root / 'foreign')
        with pytest.raises(OSError):
            bootstrap.bootstrap(config, HEAD, filesystem_root=root)
