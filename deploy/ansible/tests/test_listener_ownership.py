"""Deterministic tests for the Reviewer loopback listener ownership contract."""

import unittest


def listener_is_accepted(listeners, expected_listener, service_active, main_pid):
    """Mirror the preflight decision: empty or fully owned expected listeners pass."""
    if not listeners:
        return True
    if not service_active or int(main_pid) <= 0:
        return False
    marker = f"pid={int(main_pid)},"
    return all(expected_listener in line and marker in line for line in listeners)


class ListenerOwnershipTests(unittest.TestCase):
    def test_empty_port_is_accepted(self):
        self.assertTrue(listener_is_accepted([], "127.0.0.1:8083", False, 0))

    def test_active_expected_reviewer_listener_is_accepted(self):
        listeners = [
            'LISTEN 0 128 127.0.0.1:8787 0.0.0.0:* users:(("reviewer-mcp-http",pid=4242,fd=7))'
        ]
        self.assertTrue(listener_is_accepted(listeners, "127.0.0.1:8787", True, 4242))

    def test_foreign_process_on_expected_address_is_rejected(self):
        listeners = [
            'LISTEN 0 128 127.0.0.1:8787 0.0.0.0:* users:(("foreign",pid=9001,fd=3))'
        ]
        self.assertFalse(listener_is_accepted(listeners, "127.0.0.1:8787", True, 4242))

    def test_public_binding_is_rejected(self):
        listeners = [
            'LISTEN 0 128 0.0.0.0:8787 0.0.0.0:* users:(("reviewer-mcp-http",pid=4242,fd=7))'
        ]
        self.assertFalse(listener_is_accepted(listeners, "127.0.0.1:8787", True, 4242))

    def test_mixed_owned_and_foreign_listeners_are_rejected(self):
        listeners = [
            'LISTEN 0 128 127.0.0.1:8787 0.0.0.0:* users:(("reviewer-mcp-http",pid=4242,fd=7))',
            'LISTEN 0 128 127.0.0.1:8787 0.0.0.0:* users:(("foreign",pid=9001,fd=3))',
        ]
        self.assertFalse(listener_is_accepted(listeners, "127.0.0.1:8787", True, 4242))


if __name__ == "__main__":
    unittest.main()
