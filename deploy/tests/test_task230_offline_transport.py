import importlib.util
from pathlib import Path
import threading
import urllib.error
import urllib.request


FIXTURE = Path(__file__).parent / 'fixtures/task230_github_https.py'
SPEC = importlib.util.spec_from_file_location('task230_github_https_fixture', FIXTURE)
TRANSPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRANSPORT)


def test_exact_pinned_runner_release_uses_local_fixture_bytes(tmp_path):
    archive_name = 'actions-runner-linux-x64-2.338.2.tar.gz'
    payload = b'synthetic task230 runner archive\n'
    (tmp_path / archive_name).write_bytes(payload)
    TRANSPORT.ROOT = tmp_path
    server = TRANSPORT.ThreadingHTTPServer(('127.0.0.1', 0), TRANSPORT.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = ('http://127.0.0.1:{}/actions/runner/releases/download/v2.338.2/'
               'actions-runner-linux-x64-2.338.2.tar.gz').format(server.server_port)
        with urllib.request.urlopen(url, timeout=3) as response:
            assert response.read() == payload
        assert (tmp_path / 'requests.log').read_text() == (
            'GET /actions/runner/releases/download/v2.338.2/'
            'actions-runner-linux-x64-2.338.2.tar.gz\n')
        wrong_version = url.replace('v2.338.2/', 'v2.338.3/').replace(
            'linux-x64-2.338.2', 'linux-x64-2.338.3')
        try:
            urllib.request.urlopen(wrong_version, timeout=3)
        except urllib.error.HTTPError as error:
            assert error.code == 404
        else:
            raise AssertionError('The transport served an unprovided Runner version')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
