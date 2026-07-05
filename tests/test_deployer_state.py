import importlib.util
import contextlib
import io
import pathlib
import sqlite3
import tempfile
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

    def test_print_last_links_rebuilds_from_state_before_stale_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = pathlib.Path(tmp) / "state.json"
            links_path = pathlib.Path(tmp) / "links.txt"
            old_state_path = self.module.STATE_PATH
            old_links_path = self.module.LAST_LINKS_PATH
            self.module.STATE_PATH = str(state_path)
            self.module.LAST_LINKS_PATH = str(links_path)
            try:
                state_path.write_text(
                    """
                    {
                      "domain": "node.example.com",
                      "uuid": "00000000-0000-0000-0000-000000000000",
                      "deployer_cf_url": "https://worker.example.com",
                      "routes": [
                        {"protocol": "vless", "port": 30001, "path": "/abc12345-vl"},
                        {"protocol": "trojan", "port": 30002, "path": "/abc12345-tr"}
                      ],
                      "selected_protocols": ["vless", "trojan"],
                      "links": {
                        "vless": "stale-vless",
                        "trojan": "stale-trojan",
                        "vmess": "stale-vmess"
                      }
                    }
                    """,
                    encoding="utf-8",
                )
                links_path.write_text(
                    "VMESS subscription https://worker.example.com/uuid/sub?evm=yes\n",
                    encoding="utf-8",
                )

                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.module.print_last_links()

                text = output.getvalue()
                self.assertIn("VLESS subscription", text)
                self.assertIn("TROJAN subscription", text)
                self.assertNotIn("VMESS subscription", text)
                self.assertNotIn("evm=", text)
                self.assertNotIn("stale-", text)
                self.assertNotIn("VMESS subscription", links_path.read_text(encoding="utf-8"))
            finally:
                self.module.STATE_PATH = old_state_path
                self.module.LAST_LINKS_PATH = old_links_path

    def test_close_firewall_ports_removes_broad_allow_rules(self):
        commands = []
        old_ufw = self.module.ufw_is_active
        old_firewalld = self.module.firewalld_is_active
        old_run = self.module.run_firewall_command
        self.module.ufw_is_active = lambda: True
        self.module.firewalld_is_active = lambda: True

        def fake_run(args, quiet=False):
            commands.append((args, quiet))
            return True

        self.module.run_firewall_command = fake_run
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.module.close_firewall_ports_if_active([30003, 30003])
        finally:
            self.module.ufw_is_active = old_ufw
            self.module.firewalld_is_active = old_firewalld
            self.module.run_firewall_command = old_run

        self.assertIn((["ufw", "delete", "allow", "30003/tcp"], True), commands)
        self.assertIn((["firewall-cmd", "--permanent", "--remove-port", "30003/tcp"], True), commands)
        self.assertIn((["firewall-cmd", "--reload"], True), commands)

    def test_delete_inbounds_db_uses_tags_when_state_ids_are_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = pathlib.Path(tmp) / "x-ui.db"
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("CREATE TABLE inbounds (id INTEGER PRIMARY KEY, tag TEXT)")
                conn.execute("INSERT INTO inbounds (id, tag) VALUES (?, ?)", (203, "abc12345-vmess"))
                conn.commit()
            finally:
                conn.close()

            self.module.delete_inbounds_db(str(db_path), [103], ["abc12345-vmess"])

            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute("SELECT id, tag FROM inbounds").fetchall()
            finally:
                conn.close()

        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
