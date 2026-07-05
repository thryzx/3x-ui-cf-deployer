import importlib.util
import pathlib
import unittest
from urllib import parse


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "xui_cf_deployer.py"


def load_module():
    spec = importlib.util.spec_from_file_location("xui_cf_deployer", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DeployerStateTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_vmess_subscription_uses_worker_mess_flag(self):
        links = self.module.build_links(
            "00000000-0000-0000-0000-000000000000",
            "node.example.com",
            [{"protocol": "vmess", "port": 30003, "path": "/abc12345-vm"}],
            "https://worker.example.com",
        )

        parsed = parse.urlparse(links["vmess"])
        params = parse.parse_qs(parsed.query)

        self.assertEqual(params["mess"], ["yes"])
        self.assertNotIn("evm", params)
        self.assertEqual(params["ev"], ["no"])
        self.assertEqual(params["et"], ["no"])

    def test_prune_deployment_state_removes_only_selected_protocol(self):
        state = {
            "version": 1,
            "backend": "db",
            "domain": "node.example.com",
            "zone_id": "zone-id",
            "uuid": "00000000-0000-0000-0000-000000000000",
            "short_id": "abc12345",
            "deployer_cf_url": "https://worker.example.com",
            "routes": [
                {"protocol": "vless", "port": 30001, "path": "/abc12345-vl"},
                {"protocol": "trojan", "port": 30002, "path": "/abc12345-tr"},
                {"protocol": "vmess", "port": 30003, "path": "/abc12345-vm"},
            ],
            "inbound_ids": [101, 102, 103],
            "tags": ["abc12345-vless", "abc12345-trojan", "abc12345-vmess"],
            "links": {
                "vless": "https://worker.example.com/vless",
                "trojan": "https://worker.example.com/trojan",
                "vmess": "https://worker.example.com/vmess",
            },
            "selected_protocols": ["vless", "trojan", "vmess"],
            "managed_dns_record_id": "dns-id",
        }

        next_state, removed = self.module.prune_deployment_state_protocols(state, ["vmess"])

        self.assertEqual(
            [route["protocol"] for route in next_state["routes"]],
            ["vless", "trojan"],
        )
        self.assertEqual(next_state["inbound_ids"], [101, 102])
        self.assertEqual(next_state["tags"], ["abc12345-vless", "abc12345-trojan"])
        self.assertEqual(set(next_state["links"].keys()), {"vless", "trojan"})
        self.assertEqual(next_state["selected_protocols"], ["vless", "trojan"])
        self.assertEqual(next_state["managed_dns_record_id"], "dns-id")

        self.assertEqual(removed["routes"], [{"protocol": "vmess", "port": 30003, "path": "/abc12345-vm"}])
        self.assertEqual(removed["inbound_ids"], [103])
        self.assertEqual(removed["tags"], ["abc12345-vmess"])
        self.assertEqual(removed["links"], {"vmess": "https://worker.example.com/vmess"})
        self.assertEqual(removed["protocols"], ["vmess"])


if __name__ == "__main__":
    unittest.main()
