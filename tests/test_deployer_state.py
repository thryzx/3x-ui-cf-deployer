import importlib.util
import contextlib
import io
import json
import pathlib
import sqlite3
import tempfile
import unittest
from urllib import parse


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "xui_cf_deployer.py"


def json_clone(value):
    return json.loads(json.dumps(value))


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

    def test_delete_inbounds_db_continues_when_client_schema_differs(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = pathlib.Path(tmp) / "x-ui.db"
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("CREATE TABLE inbounds (id INTEGER PRIMARY KEY, tag TEXT)")
                conn.execute("CREATE TABLE clients (id INTEGER PRIMARY KEY)")
                conn.execute("CREATE TABLE client_inbounds (client_id INTEGER, inbound_id INTEGER)")
                conn.execute("INSERT INTO inbounds (id, tag) VALUES (?, ?)", (203, "abc12345-vmess"))
                conn.execute("INSERT INTO clients (id) VALUES (?)", (77,))
                conn.execute("INSERT INTO client_inbounds (client_id, inbound_id) VALUES (?, ?)", (77, 203))
                conn.commit()
            finally:
                conn.close()

            self.module.delete_inbounds_db(str(db_path), [203], ["abc12345-vmess"])

            conn = sqlite3.connect(db_path)
            try:
                inbounds = conn.execute("SELECT id FROM inbounds").fetchall()
                links = conn.execute("SELECT client_id, inbound_id FROM client_inbounds").fetchall()
            finally:
                conn.close()

        self.assertEqual(inbounds, [])
        self.assertEqual(links, [])

    def test_remove_last_state_also_removes_subscription_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = pathlib.Path(tmp) / "state.json"
            links_path = pathlib.Path(tmp) / "links.txt"
            state_path.write_text("{}", encoding="utf-8")
            links_path.write_text("stale subscription\n", encoding="utf-8")

            old_state_path = self.module.STATE_PATH
            old_links_path = self.module.LAST_LINKS_PATH
            self.module.STATE_PATH = str(state_path)
            self.module.LAST_LINKS_PATH = str(links_path)
            try:
                self.module.remove_last_state()
                self.assertFalse(state_path.exists())
                self.assertFalse(links_path.exists())
            finally:
                self.module.STATE_PATH = old_state_path
                self.module.LAST_LINKS_PATH = old_links_path

    def test_run_deploy_install_adds_missing_protocol_to_existing_state(self):
        old_load_last_state = self.module.load_last_state
        old_configure_panel = self.module.configure_existing_panel_cloudflare
        old_resolve_backend = self.module.resolve_backend
        old_setup_panel = self.module.setup_panel_client
        old_load_ports = self.module.load_existing_ports_api
        old_random_ports = self.module.random_ports
        old_get_dns = self.module.get_dns_record
        old_get_rules = self.module.get_origin_rules
        old_create = self.module.create_inbounds
        old_upsert_dns = self.module.upsert_dns_record
        old_ssl = self.module.apply_ssl_config_rules
        old_origin = self.module.apply_origin_rules
        old_firewall = self.module.open_cloudflare_origin_ports_if_active
        old_sync_firewall = self.module.sync_cloudflare_origin_firewall_ports
        old_save_links = self.module.save_last_links_snapshot
        old_save_state = self.module.save_last_state

        saved_states = []
        origin_routes = []
        created_routes = []
        opened_ports = []

        existing_state = {
            "version": 1,
            "backend": self.module.BACKEND_DB,
            "domain": "node.example.com",
            "zone_id": "zone-id",
            "uuid": "00000000-0000-0000-0000-000000000000",
            "short_id": "abc12345",
            "deployer_cf_url": "https://worker.example.com",
            "routes": [
                {"protocol": "vless", "port": 30001, "path": "/abc12345-vl"},
                {"protocol": "trojan", "port": 30002, "path": "/abc12345-tr"},
            ],
            "inbound_ids": [101, 102],
            "tags": ["abc12345-vless", "abc12345-trojan"],
            "selected_protocols": ["vless", "trojan"],
            "links": {},
            "managed_dns_record_id": "dns-id",
            "dns_backup": {"existed": False},
        }

        context = {
            "deployer_cf_url": "https://worker.example.com",
            "domain": "node.example.com",
            "selected_protocols": ["vless", "trojan", "vmess"],
            "headers": {"Authorization": "Bearer token"},
            "zone_id": "zone-id",
            "public_ip": "203.0.113.10",
            "panel_domain": "",
        }

        self.module.load_last_state = lambda: json_clone(existing_state)
        self.module.configure_existing_panel_cloudflare = lambda context: None
        self.module.resolve_backend = lambda state=None: (self.module.BACKEND_API, {}, "test")
        self.module.setup_panel_client = lambda runtime, interactive=False: object()
        self.module.load_existing_ports_api = lambda panel: {30001, 30002}
        self.module.random_ports = lambda count, existing: [30003]
        self.module.get_dns_record = lambda zone_id, domain, headers: {"id": "dns-id"}
        self.module.get_origin_rules = lambda zone_id, headers: [{"description": "external"}]
        self.module.create_inbounds = lambda backend, user_uuid, short_id, routes, panel=None: (
            created_routes.extend(json_clone(routes)) or [103]
        )
        self.module.upsert_dns_record = lambda zone_id, domain, public_ip, headers: "dns-id"
        self.module.apply_ssl_config_rules = lambda zone_id, headers, rules: None
        self.module.apply_origin_rules = lambda zone_id, headers, domain, routes: origin_routes.extend(json_clone(routes))
        self.module.open_cloudflare_origin_ports_if_active = lambda ports: opened_ports.extend(ports)
        self.module.sync_cloudflare_origin_firewall_ports = lambda ports: None
        self.module.save_last_links_snapshot = lambda domain, user_uuid, links, order: None
        self.module.save_last_state = lambda state: saved_states.append(json_clone(state))
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.module.run_deploy_install(context)
        finally:
            self.module.load_last_state = old_load_last_state
            self.module.configure_existing_panel_cloudflare = old_configure_panel
            self.module.resolve_backend = old_resolve_backend
            self.module.setup_panel_client = old_setup_panel
            self.module.load_existing_ports_api = old_load_ports
            self.module.random_ports = old_random_ports
            self.module.get_dns_record = old_get_dns
            self.module.get_origin_rules = old_get_rules
            self.module.create_inbounds = old_create
            self.module.upsert_dns_record = old_upsert_dns
            self.module.apply_ssl_config_rules = old_ssl
            self.module.apply_origin_rules = old_origin
            self.module.open_cloudflare_origin_ports_if_active = old_firewall
            self.module.sync_cloudflare_origin_firewall_ports = old_sync_firewall
            self.module.save_last_links_snapshot = old_save_links
            self.module.save_last_state = old_save_state

        self.assertEqual([route["protocol"] for route in created_routes], ["vmess"])
        self.assertEqual([route["protocol"] for route in origin_routes], ["vless", "trojan", "vmess"])
        self.assertEqual(opened_ports, [30003])
        self.assertEqual([route["protocol"] for route in saved_states[-1]["routes"]], ["vless", "trojan", "vmess"])
        self.assertEqual(saved_states[-1]["inbound_ids"], [101, 102, 103])
        self.assertIn("vmess", saved_states[-1]["links"])

    def test_delete_deployed_protocols_updates_state_rules_and_firewall(self):
        old_get_rules = self.module.get_origin_rules
        old_put_rules = self.module.put_origin_rules
        old_delete = self.module.delete_managed_inbounds
        old_close = self.module.close_firewall_ports_if_active
        old_sync = self.module.sync_cloudflare_origin_firewall_ports
        old_save_state = self.module.save_last_state
        old_save_links = self.module.save_last_links_snapshot

        saved_states = []
        put_rules = []
        deleted = []
        closed_ports = []
        synced_ports = []

        state = {
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
            "selected_protocols": ["vless", "trojan", "vmess"],
        }

        self.module.get_origin_rules = lambda zone_id, headers: [{"description": "external"}]
        self.module.put_origin_rules = lambda zone_id, headers, rules: put_rules.extend(json_clone(rules))
        self.module.delete_managed_inbounds = lambda backend, ids, tags, panel=None: deleted.append((backend, ids, tags))
        self.module.close_firewall_ports_if_active = lambda ports: closed_ports.extend(ports)
        self.module.sync_cloudflare_origin_firewall_ports = lambda ports: synced_ports.extend(ports)
        self.module.save_last_state = lambda next_state: saved_states.append(json_clone(next_state))
        self.module.save_last_links_snapshot = lambda domain, user_uuid, links, order: None
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.module.delete_deployed_protocols(
                    state,
                    ["vmess"],
                    {"Authorization": "Bearer token"},
                    self.module.BACKEND_DB,
                )
        finally:
            self.module.get_origin_rules = old_get_rules
            self.module.put_origin_rules = old_put_rules
            self.module.delete_managed_inbounds = old_delete
            self.module.close_firewall_ports_if_active = old_close
            self.module.sync_cloudflare_origin_firewall_ports = old_sync
            self.module.save_last_state = old_save_state
            self.module.save_last_links_snapshot = old_save_links

        self.assertEqual(deleted, [(self.module.BACKEND_DB, [103], ["abc12345-vmess"])])
        self.assertEqual(closed_ports, [30003])
        self.assertEqual(synced_ports, [30001, 30002])
        self.assertEqual([route["protocol"] for route in saved_states[-1]["routes"]], ["vless", "trojan"])
        self.assertEqual(set(saved_states[-1]["links"].keys()), {"vless", "trojan"})
        self.assertNotIn("abc12345-vm", json.dumps(put_rules))

    def test_uninstall_closes_all_ports_and_syncs_empty_firewall(self):
        old_get_rules = self.module.get_origin_rules
        old_put_rules = self.module.put_origin_rules
        old_remove_ssl = self.module.remove_ssl_config_rules_for_domain
        old_restore_dns = self.module.restore_dns_record
        old_delete = self.module.delete_managed_inbounds
        old_close = self.module.close_firewall_ports_if_active
        old_sync = self.module.sync_cloudflare_origin_firewall_ports

        deleted = []
        closed_ports = []
        synced_ports = []
        put_rules = []

        state = {
            "domain": "node.example.com",
            "zone_id": "zone-id",
            "routes": [
                {"protocol": "vless", "port": 30001, "path": "/abc12345-vl"},
                {"protocol": "trojan", "port": 30002, "path": "/abc12345-tr"},
            ],
            "inbound_ids": [101, 102],
            "tags": ["abc12345-vless", "abc12345-trojan"],
            "managed_dns_record_id": "dns-id",
            "dns_backup": {"existed": False},
        }

        self.module.get_origin_rules = lambda zone_id, headers: [
            {"description": "external"},
            {"description": self.module.MANAGED_RULE_PREFIX + "vless /abc12345-vl", "expression": '(http.host eq "node.example.com")'},
        ]
        self.module.put_origin_rules = lambda zone_id, headers, rules: put_rules.extend(json_clone(rules))
        self.module.remove_ssl_config_rules_for_domain = lambda zone_id, headers, domain: None
        self.module.restore_dns_record = lambda **kwargs: None
        self.module.delete_managed_inbounds = lambda backend, ids, tags, panel=None: deleted.append((backend, ids, tags))
        self.module.close_firewall_ports_if_active = lambda ports: closed_ports.extend(ports)
        self.module.sync_cloudflare_origin_firewall_ports = lambda ports: synced_ports.extend(ports)
        try:
            self.module.uninstall_last_config(
                state,
                {"Authorization": "Bearer token"},
                self.module.BACKEND_DB,
            )
        finally:
            self.module.get_origin_rules = old_get_rules
            self.module.put_origin_rules = old_put_rules
            self.module.remove_ssl_config_rules_for_domain = old_remove_ssl
            self.module.restore_dns_record = old_restore_dns
            self.module.delete_managed_inbounds = old_delete
            self.module.close_firewall_ports_if_active = old_close
            self.module.sync_cloudflare_origin_firewall_ports = old_sync

        self.assertEqual(deleted, [(self.module.BACKEND_DB, [101, 102], ["abc12345-vless", "abc12345-trojan"])])
        self.assertEqual(closed_ports, [30001, 30002])
        self.assertEqual(synced_ports, [])
        self.assertEqual(put_rules, [{"description": "external"}])


if __name__ == "__main__":
    unittest.main()
