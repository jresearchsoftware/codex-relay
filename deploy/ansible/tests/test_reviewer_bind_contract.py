"""Deterministic tests for the admitted TCP-only Reviewer bind modes."""

import ipaddress
import unittest


def reviewer_bind_is_admitted(mode, address, network="", gateway_validated=False):
    if mode == "a_only_loopback":
        return address == "127.0.0.1" and network == "" and not gateway_validated
    if mode == "nexus_gateway":
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            return False
        return (
            parsed.version == 4
            and network == "nexus"
            and gateway_validated
            and not parsed.is_loopback
            and not parsed.is_unspecified
            and not parsed.is_multicast
            and address != "255.255.255.255"
        )
    return False


def nexus_gateway_is_admitted(network, nginx_network, host_addresses, route_ok):
    if not network or network.get("Name") != "nexus" or network.get("Driver") != "bridge":
        return False
    configs = network.get("IPAM", {}).get("Config", [])
    if len(configs) != 1:
        return False
    gateway = configs[0].get("Gateway")
    if not reviewer_bind_is_admitted("nexus_gateway", gateway, "nexus", True):
        return False
    return (
        host_addresses.count(gateway) == 1
        and route_ok
        and nginx_network.get("NetworkID") == network.get("Id")
        and nginx_network.get("Gateway") == gateway
    )


class ReviewerBindContractTests(unittest.TestCase):
    def test_loopback_tcp_is_the_only_a_only_transport(self):
        self.assertTrue(reviewer_bind_is_admitted("a_only_loopback", "127.0.0.1"))
        self.assertFalse(reviewer_bind_is_admitted("a_only_loopback", "192.168.1.10"))
        self.assertFalse(reviewer_bind_is_admitted("a_only_unix_socket", ""))
        self.assertFalse(reviewer_bind_is_admitted("a_only_loopback", "", ""))

    def test_coexistence_accepts_only_validated_nexus_gateway(self):
        self.assertTrue(reviewer_bind_is_admitted("nexus_gateway", "172.18.0.1", "nexus", True))
        self.assertFalse(reviewer_bind_is_admitted("nexus_gateway", "0.0.0.0", "nexus", True))
        self.assertFalse(reviewer_bind_is_admitted("nexus_gateway", "192.0.2.10", "other", True))
        self.assertFalse(reviewer_bind_is_admitted("nexus_gateway", "172.18.0.1", "nexus", False))

    def test_gateway_requires_exact_network_unique_local_address_and_route(self):
        network = {"Name": "nexus", "Driver": "bridge", "Id": "network-id", "IPAM": {"Config": [{"Gateway": "172.18.0.1"}]}}
        nginx_network = {"NetworkID": "network-id", "Gateway": "172.18.0.1"}
        self.assertTrue(nexus_gateway_is_admitted(network, nginx_network, ["172.18.0.1"], True))
        self.assertFalse(nexus_gateway_is_admitted({}, nginx_network, ["172.18.0.1"], True))
        ambiguous = {**network, "IPAM": {"Config": [{"Gateway": "172.18.0.1"}, {"Gateway": "172.19.0.1"}]}}
        self.assertFalse(nexus_gateway_is_admitted(ambiguous, nginx_network, ["172.18.0.1"], True))
        self.assertFalse(nexus_gateway_is_admitted(network, nginx_network, ["172.18.0.1", "172.18.0.1"], True))
        self.assertFalse(nexus_gateway_is_admitted(network, nginx_network, ["172.18.0.1"], False))


if __name__ == "__main__":
    unittest.main()
