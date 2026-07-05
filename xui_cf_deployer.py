#!/usr/bin/env python3
import http.cookiejar
import ipaddress
import json
import os
import random
import re
import shutil
import socket
import sqlite3
import ssl
import subprocess
import sys
import time
import uuid
from getpass import getpass
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib import error, parse, request
from urllib.request import HTTPCookieProcessor, HTTPSHandler, build_opener

try:
    import termios
    import tty

    HAS_TERMIOS = True
except ImportError:
    HAS_TERMIOS = False


DB_PATH = "/etc/x-ui/x-ui.db"
STATE_PATH = "/etc/x-ui/cf_auto_state.json"
CF_ACCOUNT_PATH = "/etc/x-ui/cf_account.json"
DEPLOYER_CONFIG_PATH = "/etc/x-ui/cf_deployer_config.json"
CF_IP_CACHE_PATH = "/etc/x-ui/cf_cloudflare_ips.json"
CF_FIREWALL_STATE_PATH = "/etc/x-ui/cf_firewall_state.json"
PANEL_INFO_PATH = "/etc/x-ui/cf_panel_access.json"
LAST_LINKS_PATH = os.path.join(os.getcwd(), "cf_auto_last_links.txt")
PANEL_INFO_SNAPSHOT = os.path.join(os.getcwd(), "cf_panel_last_access.txt")
CFD_BIN = "/usr/local/bin/cfd"
DEPLOYER_INSTALL_PATH = "/usr/local/lib/cf-deployer/xui_cf_deployer.py"
CF_FIREWALL_SERVICE = "cf-deployer-cloudflare-firewall.service"
CF_FIREWALL_TIMER = "cf-deployer-cloudflare-firewall.timer"
CF_FIREWALL_SERVICE_PATH = f"/etc/systemd/system/{CF_FIREWALL_SERVICE}"
CF_FIREWALL_TIMER_PATH = f"/etc/systemd/system/{CF_FIREWALL_TIMER}"
XUI_INSTALL_URL = "https://raw.githubusercontent.com/mhsanaei/3x-ui/master/install.sh"
XUI_INSTALL_STDIN = "\nn\n4\n\n"
CF_API_BASE = "https://api.cloudflare.com/client/v4"
CF_IPS_V4_URL = "https://www.cloudflare.com/ips-v4"
CF_IPS_V6_URL = "https://www.cloudflare.com/ips-v6"
DEFAULT_PANEL_URL = "http://127.0.0.1:2053"
DEFAULT_DEPLOYER_CF_URL = "https://yx-auto.pages.dev"
DEPLOYER_CF_URL_ENV = "DEPLOYER_CF_URL"
LEGACY_DEPLOYER_CF_URL_ENV = "YX_AUTO_BASE_URL"
PORT_MIN = 10000
PORT_MAX = 60000
PROTOCOL_ORDER = ["vless", "trojan", "vmess"]
PROTOCOL_SUFFIX = {"vless": "vl", "trojan": "tr", "vmess": "vm"}
PROTOCOL_LABEL = {"vless": "VLESS", "trojan": "TROJAN", "vmess": "VMESS"}
PROTOCOL_QUERY_FLAG = {"vless": "ev", "trojan": "et", "vmess": "evm"}
MANAGED_RULE_PREFIX = "3x-ui-auto "
MANAGED_SSL_RULE_PREFIX = "3x-ui-auto ssl "
ORIGIN_RULE_PHASE = "http_request_origin"
CONFIG_RULE_PHASE = "http_config_settings"
CF_SUPPORTED_HTTPS_PORTS = [443, 2053, 2083, 2087, 2096, 8443]
FIREWALL_PANEL_PORTS = [80, 443]
CF_FALLBACK_IP_RANGES = [
    "173.245.48.0/20",
    "103.21.244.0/22",
    "103.22.200.0/22",
    "103.31.4.0/22",
    "141.101.64.0/18",
    "108.162.192.0/18",
    "190.93.240.0/20",
    "188.114.96.0/20",
    "197.234.240.0/22",
    "198.41.128.0/17",
    "162.158.0.0/15",
    "104.16.0.0/13",
    "104.24.0.0/14",
    "172.64.0.0/13",
    "131.0.72.0/22",
    "2400:cb00::/32",
    "2606:4700::/32",
    "2803:f800::/32",
    "2405:b500::/32",
    "2405:8100::/32",
    "2a06:98c0::/29",
    "2c0f:f248::/32",
]
MANAGED_TAG_RE = re.compile(r"^([0-9a-f]{8})-(vless|trojan|vmess)$", re.I)
PANEL_API_PREFIX = "panel/api"
BACKEND_DB = "db"
BACKEND_API = "api"
API_MIN_VERSION = (2, 0, 0)
XUI_BINARY_CANDIDATES = ("/usr/local/x-ui/x-ui", "/usr/bin/x-ui")
XUI_CLI_SCRIPT_CANDIDATES = ("/usr/bin/x-ui", "/usr/local/x-ui/x-ui.sh")
XUI_MENU_ZH_MARKER = "# cf-deployer-xui-menu-zh"
XUI_MENU_REPLACEMENTS: List[tuple[str, str]] = [
    ('echo "The OS release is: $release"', 'echo "\u7cfb\u7edf\u53d1\u884c\u7248: $release"'),
    ("3X-UI Panel Management Script", "3X-UI \u9762\u677f\u7ba1\u7406\u811a\u672c"),
    ("0.${plain} Exit Script", "0.${plain} \u9000\u51fa\u811a\u672c"),
    ("1.${plain} Install", "1.${plain} \u5b89\u88c5"),
    ("2.${plain} Update", "2.${plain} \u66f4\u65b0"),
    ("3.${plain} Update Menu", "3.${plain} \u66f4\u65b0\u83dc\u5355"),
    ("4.${plain} Legacy Version", "4.${plain} \u65e7\u7248\u5b89\u88c5"),
    ("5.${plain} Uninstall", "5.${plain} \u5378\u8f7d"),
    ("6.${plain} Reset Username & Password", "6.${plain} \u91cd\u7f6e\u7528\u6237\u540d\u548c\u5bc6\u7801"),
    ("7.${plain} Reset Web Base Path", "7.${plain} \u91cd\u7f6e\u9762\u677f\u8bbf\u95ee\u8def\u5f84"),
    ("8.${plain} Reset Settings", "8.${plain} \u91cd\u7f6e\u9762\u677f\u8bbe\u7f6e"),
    ("9.${plain} Change Port", "9.${plain} \u4fee\u6539\u9762\u677f\u7aef\u53e3"),
    ("10.${plain} View Current Settings", "10.${plain} \u67e5\u770b\u5f53\u524d\u8bbe\u7f6e"),
    ("11.${plain} Start", "11.${plain} \u542f\u52a8"),
    ("12.${plain} Stop", "12.${plain} \u505c\u6b62"),
    ("13.${plain} Restart", "13.${plain} \u91cd\u542f"),
    ("14.${plain} Restart Xray", "14.${plain} \u91cd\u542f Xray"),
    ("15.${plain} Check Status", "15.${plain} \u67e5\u770b\u72b6\u6001"),
    ("16.${plain} Logs Management", "16.${plain} \u65e5\u5fd7\u7ba1\u7406"),
    ("17.${plain} Enable Autostart", "17.${plain} \u542f\u7528\u5f00\u673a\u81ea\u542f"),
    ("18.${plain} Disable Autostart", "18.${plain} \u7981\u7528\u5f00\u673a\u81ea\u542f"),
    ("19.${plain} SSL Certificate Management", "19.${plain} SSL \u8bc1\u4e66\u7ba1\u7406"),
    ("20.${plain} Cloudflare SSL Certificate", "20.${plain} Cloudflare SSL \u8bc1\u4e66"),
    ("21.${plain} IP Limit Management", "21.${plain} IP \u9650\u5236\u7ba1\u7406"),
    ("22.${plain} Firewall Management", "22.${plain} \u9632\u706b\u5899\u7ba1\u7406"),
    ("23.${plain} SSH Port Forwarding Management", "23.${plain} SSH \u7aef\u53e3\u8f6c\u53d1\u7ba1\u7406"),
    ("24.${plain} Enable BBR", "24.${plain} \u542f\u7528 BBR"),
    ("25.${plain} Update Geo Files", "25.${plain} \u66f4\u65b0 Geo \u6587\u4ef6"),
    ("26.${plain} Speedtest by Ookla", "26.${plain} Ookla \u6d4b\u901f"),
    ("27.${plain} PostgreSQL Management", "27.${plain} PostgreSQL \u7ba1\u7406"),
    ('read -rp "Please enter your selection [0-27]: " num', 'read -rp "\u8bf7\u8f93\u5165\u9009\u9879 [0-27]: " num'),
    ('LOGE "Please enter the correct number [0-27]"', 'LOGE "\u8bf7\u8f93\u5165\u6b63\u786e\u9009\u9879 [0-27]"'),
    ('echo -e "Panel state: ${green}Running${plain}"', 'echo -e "\u9762\u677f\u72b6\u6001: ${green}\u8fd0\u884c\u4e2d${plain}"'),
    ('echo -e "Panel state: ${yellow}Not Running${plain}"', 'echo -e "\u9762\u677f\u72b6\u6001: ${yellow}\u672a\u8fd0\u884c${plain}"'),
    ('echo -e "Panel state: ${red}Not Installed${plain}"', 'echo -e "\u9762\u677f\u72b6\u6001: ${red}\u672a\u5b89\u88c5${plain}"'),
    ('echo -e "Start automatically: ${green}Yes${plain}"', 'echo -e "\u5f00\u673a\u81ea\u542f: ${green}\u662f${plain}"'),
    ('echo -e "Start automatically: ${red}No${plain}"', 'echo -e "\u5f00\u673a\u81ea\u542f: ${red}\u5426${plain}"'),
    ('echo -e "xray state: ${green}Running${plain}"', 'echo -e "xray \u72b6\u6001: ${green}\u8fd0\u884c\u4e2d${plain}"'),
    ('echo -e "xray state: ${red}Not Running${plain}"', 'echo -e "xray \u72b6\u6001: ${red}\u672a\u8fd0\u884c${plain}"'),
]


def exit_error(message: str) -> None:
    print(message)
    sys.exit(1)


def call_json_api(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    data: Optional[Dict[str, Any]] = None,
    timeout: int = 20,
    exit_on_http_error: bool = True,
    opener: Optional[Any] = None,
):
    payload = None
    if data is not None:
        payload = json.dumps(data).encode("utf-8")

    req = request.Request(url=url, data=payload, headers=headers or {}, method=method)

    open_fn = opener.open if opener is not None else request.urlopen
    try:
        with open_fn(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        if exit_on_http_error:
            print(body)
            sys.exit(1)
        if body:
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {"success": False, "errors": [{"message": body}]}
        return {"success": False, "errors": [{"message": f"HTTP {e.code}"}]}
    except error.URLError as e:
        exit_error(f"Network error: {e}")

    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"raw": body}


def call_cf_api(
    method: str,
    endpoint: str,
    headers: Dict[str, str],
    data: Optional[Dict[str, Any]] = None,
):
    result = call_json_api(method=method, url=f"{CF_API_BASE}{endpoint}", headers=headers, data=data)
    if not result.get("success", False):
        errors = result.get("errors") or [{"message": "Unknown Cloudflare API error"}]
        print(json.dumps(errors, ensure_ascii=False))
        sys.exit(1)
    return result.get("result")


def call_cf_api_result(
    method: str,
    endpoint: str,
    headers: Dict[str, str],
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return call_json_api(
        method=method,
        url=f"{CF_API_BASE}{endpoint}",
        headers=headers,
        data=data,
        exit_on_http_error=False,
    )


def normalize_deployer_cf_url(value: str) -> str:
    url = value.strip().rstrip("/")
    parsed = parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        exit_error("Deployer CF URL must be a complete http(s) URL")
    return url


def load_deployer_config() -> Dict[str, Any]:
    if not os.path.isfile(DEPLOYER_CONFIG_PATH):
        return {}
    try:
        with open(DEPLOYER_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_deployer_config(config: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(DEPLOYER_CONFIG_PATH), exist_ok=True)
        with open(DEPLOYER_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        os.chmod(DEPLOYER_CONFIG_PATH, 0o600)
    except OSError as e:
        exit_error(f"Failed to save deployer config: {e}")


def resolve_deployer_cf_url() -> str:
    env_url = (
        os.environ.get(DEPLOYER_CF_URL_ENV, "").strip()
        or os.environ.get(LEGACY_DEPLOYER_CF_URL_ENV, "").strip()
    )
    if env_url:
        url = normalize_deployer_cf_url(env_url)
        os.environ[DEPLOYER_CF_URL_ENV] = url
        return url

    config = load_deployer_config()
    configured = str(config.get("deployer_cf_url") or "").strip()
    if configured:
        url = normalize_deployer_cf_url(configured)
        os.environ[DEPLOYER_CF_URL_ENV] = url
        return url

    raw = input(f"Deployer CF URL(Enter={DEFAULT_DEPLOYER_CF_URL}): ").strip()
    url = normalize_deployer_cf_url(raw or DEFAULT_DEPLOYER_CF_URL)
    config["deployer_cf_url"] = url
    save_deployer_config(config)
    os.environ[DEPLOYER_CF_URL_ENV] = url
    print(f"Deployer CF URL saved to {DEPLOYER_CONFIG_PATH}")
    return url


def current_deployer_cf_url(state: Optional[Dict[str, Any]] = None) -> str:
    if state:
        saved = str(state.get("deployer_cf_url") or "").strip()
        if saved:
            return normalize_deployer_cf_url(saved)
    env_url = (
        os.environ.get(DEPLOYER_CF_URL_ENV, "").strip()
        or os.environ.get(LEGACY_DEPLOYER_CF_URL_ENV, "").strip()
    )
    if env_url:
        return normalize_deployer_cf_url(env_url)
    configured = str(load_deployer_config().get("deployer_cf_url") or "").strip()
    if configured:
        return normalize_deployer_cf_url(configured)
    return DEFAULT_DEPLOYER_CF_URL


def build_cf_headers(api_token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }


def normalize_domain(value: str) -> str:
    domain = value.strip().strip(".").lower()
    if not domain or "." not in domain or any(ch.isspace() for ch in domain):
        exit_error("Invalid domain format")
    return domain


def default_panel_domain_for(node_domain: str, zone_name: str) -> str:
    zone = normalize_domain(zone_name)
    candidate = f"panel.{zone}"
    if normalize_domain(node_domain) == candidate:
        return f"xui.{zone}"
    return candidate


def is_tcp_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def choose_cloudflare_panel_port(preferred: Optional[int] = None) -> int:
    candidates = list(CF_SUPPORTED_HTTPS_PORTS)
    if preferred in candidates:
        candidates.remove(preferred)  # type: ignore[arg-type]
        candidates.insert(0, preferred)  # type: ignore[arg-type]
    else:
        random.shuffle(candidates)
    for port in candidates:
        if is_tcp_port_available(port):
            return port
    exit_error("No available Cloudflare-supported HTTPS port")


def current_panel_port() -> int:
    raw = read_setting_from_db("webPort") or "2053"
    try:
        return int(raw)
    except ValueError:
        return 2053


def panel_url_for_domain(domain: str, port: int) -> str:
    base_path = read_setting_from_db("webBasePath") or "/"
    if not base_path.startswith("/"):
        base_path = f"/{base_path}"
    base_path = base_path.rstrip("/") or ""
    return f"https://{domain}:{port}{base_path}"


def warn_legacy_cf_account_file() -> None:
    if os.path.exists(CF_ACCOUNT_PATH):
        print(
            f"Detected legacy Cloudflare Global API Key file {CF_ACCOUNT_PATH}. "
            "This script no longer uses it. Review and delete it manually when safe."
        )


def prompt_cf_api_token() -> str:
    warn_legacy_cf_account_file()
    token = (
        os.environ.get("CF_API_TOKEN", "").strip()
        or os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    )
    if not token:
        token = getpass("Cloudflare API Token: ").strip()
    if not token:
        exit_error("Cloudflare API Token cannot be empty")
    return token


class XuiPanelClient:
    """3x-ui panel REST API client with session login or bearer token support."""

    def __init__(self, base_url: str, token: Optional[str] = None, insecure_tls: bool = False):
        self.base_url = base_url.rstrip("/")
        self.token = (token or "").strip() or None
        self.csrf_token: Optional[str] = None
        self.insecure_tls = insecure_tls
        jar = http.cookiejar.CookieJar()
        handlers: List[Any] = [HTTPCookieProcessor(jar)]
        if insecure_tls:
            handlers.append(HTTPSHandler(context=ssl._create_unverified_context()))
        self.opener = build_opener(*handlers)

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }
        if extra:
            headers.update(extra)
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        elif self.csrf_token:
            headers["X-CSRF-Token"] = self.csrf_token
        return headers

    def _request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        *,
        require_success: bool = True,
        auth_required: bool = True,
    ) -> Dict[str, Any]:
        if auth_required and not self.token and not self.csrf_token:
            exit_error("Not logged in to the 3x-ui panel. Call login() first or provide an API Token.")

        result = call_json_api(
            method=method,
            url=self._url(path),
            headers=self._headers(),
            data=data,
            opener=self.opener,
        )
        if require_success and not result.get("success", False):
            msg = result.get("msg") or result.get("message") or json.dumps(result, ensure_ascii=False)
            exit_error(f"3x-ui API failed: {msg}")
        return result

    def fetch_csrf_token(self) -> str:
        result = self._request("GET", "csrf-token", require_success=True, auth_required=False)
        token = result.get("obj")
        if not isinstance(token, str) or not token:
            exit_error("Failed to get CSRF token")
        self.csrf_token = token
        return token

    def login(self, username: str, password: str, two_factor_code: str = "") -> None:
        self.fetch_csrf_token()
        payload: Dict[str, Any] = {"username": username, "password": password}
        if two_factor_code.strip():
            payload["twoFactorCode"] = two_factor_code.strip()
        self._request("POST", "login", data=payload, auth_required=False)
        if not self.csrf_token:
            exit_error("3x-ui login failed: CSRF token was not returned")

    def list_inbounds(self) -> List[Dict[str, Any]]:
        result = self._request("GET", f"{PANEL_API_PREFIX}/inbounds/list")
        obj = result.get("obj")
        if isinstance(obj, list):
            return obj
        return []

    def add_inbound(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = self._request("POST", f"{PANEL_API_PREFIX}/inbounds/add", data=payload)
        obj = result.get("obj")
        if isinstance(obj, dict):
            return obj
        return {}

    def delete_inbound(self, inbound_id: int) -> None:
        self._request("POST", f"{PANEL_API_PREFIX}/inbounds/del/{inbound_id}")

    def restart_xray(self) -> None:
        self._request("POST", f"{PANEL_API_PREFIX}/server/restartXrayService")


def parse_version(version_text: str) -> Tuple[int, ...]:
    parts: List[int] = []
    for token in re.split(r"[^0-9]+", version_text.strip()):
        if token.isdigit():
            parts.append(int(token))
    return tuple(parts) if parts else (0,)


def version_at_least(version_tuple: Tuple[int, ...], minimum: Tuple[int, ...]) -> bool:
    width = max(len(version_tuple), len(minimum))
    left = version_tuple + (0,) * (width - len(version_tuple))
    right = minimum + (0,) * (width - len(minimum))
    return left >= right


def find_xui_binary() -> Optional[str]:
    candidates: List[str] = []
    which = shutil.which("x-ui")
    if which:
        candidates.append(which)
    candidates.extend(XUI_BINARY_CANDIDATES)

    seen: Set[str] = set()
    for path in candidates:
        if not path or path in seen or not os.path.isfile(path):
            continue
        seen.add(path)
        try:
            result = subprocess.run(
                [path, "-v"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        version = (result.stdout or result.stderr or "").strip().splitlines()
        if version and re.match(r"^\d", version[0]):
            return path
    return None


def read_xui_version(binary: Optional[str]) -> Optional[str]:
    if not binary:
        return None
    try:
        result = subprocess.run(
            [binary, "-v"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (result.stdout or result.stderr or "").strip().splitlines()
    if not text:
        return None
    return text[0]


def read_setting_from_db(key: str) -> Optional[str]:
    if not os.path.isfile(DB_PATH):
        return None
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM settings WHERE key=?", (key,))
            row = cur.fetchone()
    except sqlite3.Error:
        return None
    if not row or row[0] is None:
        return None
    return str(row[0])


def detect_panel_url() -> Tuple[str, bool]:
    env_url = os.environ.get("XUI_PANEL_URL", "").strip()
    if env_url:
        return env_url.rstrip("/"), env_url.lower().startswith("https://")

    port = read_setting_from_db("webPort") or "2053"
    base_path = read_setting_from_db("webBasePath") or "/"
    cert = (read_setting_from_db("webCertFile") or "").strip()
    key = (read_setting_from_db("webKeyFile") or "").strip()
    https = bool(cert and key)
    if not base_path.startswith("/"):
        base_path = f"/{base_path}"
    base_path = base_path.rstrip("/") or ""
    return f"{'https' if https else 'http'}://127.0.0.1:{port}{base_path}", https


def read_api_token_from_cli(binary: Optional[str]) -> Optional[str]:
    if not binary:
        return None
    try:
        result = subprocess.run(
            [binary, "setting", "-getApiToken"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = f"{result.stdout or ''}\n{result.stderr or ''}"
    for line in output.splitlines():
        if line.startswith("apiToken:"):
            token = line.split(":", 1)[1].strip()
            return token or None
    return None


def is_xui_installed() -> bool:
    return os.path.isfile(DB_PATH) and find_xui_binary() is not None


def parse_credentials_from_install_output(output: str) -> Tuple[Optional[str], Optional[str]]:
    username: Optional[str] = None
    password: Optional[str] = None
    for line in output.splitlines():
        clean = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
        user_match = re.search(r"Username:\s*(\S+)", clean, re.I)
        if user_match:
            username = user_match.group(1)
        pass_match = re.search(r"Password:\s*(\S+)", clean, re.I)
        if pass_match:
            password = pass_match.group(1)
    return username, password


def is_password_hash(value: str) -> bool:
    return value.startswith(("$2a$", "$2b$", "$2y$"))


def run_xui_install_script(panel_port: Optional[int] = None) -> Tuple[str, str]:
    port_text = f" / panel port {panel_port}" if panel_port else " / random port"
    print(f"Installing 3x-ui (SQLite{port_text} / installer SSL disabled)...")
    env = os.environ.copy()
    env["XUI_NONINTERACTIVE"] = "1"
    env["XUI_SSL_MODE"] = "none"
    if panel_port:
        env["XUI_PANEL_PORT"] = str(panel_port)
    try:
        proc = subprocess.run(
            ["bash", "-c", f"curl -fsSL {shlex_quote(XUI_INSTALL_URL)} | bash"],
            input=XUI_INSTALL_STDIN,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        exit_error("3x-ui installation timed out")

    install_output = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    if proc.returncode != 0:
        exit_error(f"3x-ui installation failed (exit {proc.returncode}):\n{install_output.strip()[-2000:]}")

    for _ in range(45):
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "x-ui"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except OSError:
            break
        if result.stdout.strip() == "active":
            print("3x-ui installation completed and the service is active")
            username, password = parse_credentials_from_install_output(install_output)
            if not username or not password:
                exit_error("3x-ui installed but login credentials could not be parsed. Check the installer output.")
            return username, password
        time.sleep(2)
    exit_error("3x-ui installed but the service is not active. Check journalctl -u x-ui.")


def shlex_quote(value: str) -> str:
    if re.match(r"^[A-Za-z0-9_/@.+-]+$", value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


def run_checked(
    args: List[str],
    *,
    env: Optional[Dict[str, str]] = None,
    timeout: int = 120,
    error_message: str = "Command failed",
) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        exit_error(f"{error_message}: timed out")
    except OSError as e:
        exit_error(f"{error_message}: {e}")
    if proc.returncode != 0:
        output = f"{proc.stdout or ''}\n{proc.stderr or ''}".strip()
        exit_error(f"{error_message} (exit {proc.returncode}):\n{output[-2000:]}")
    return proc


def set_panel_port(port: int) -> None:
    binary = find_xui_binary()
    if not binary:
        exit_error("x-ui binary not found; cannot change panel port")
    run_checked([binary, "setting", "-port", str(port)], timeout=30, error_message="Failed to change 3x-ui panel port")
    restart_xui_service()


def ensure_cloudflare_panel_port() -> int:
    port = current_panel_port()
    if port in CF_SUPPORTED_HTTPS_PORTS:
        return port
    new_port = choose_cloudflare_panel_port()
    print(f"Current panel port {port} is not supported by Cloudflare proxied HTTPS. Switching to {new_port}")
    set_panel_port(new_port)
    return new_port


def acme_sh_path() -> str:
    home = "/root" if os.geteuid() == 0 else os.path.expanduser("~")
    return os.path.join(home, ".acme.sh", "acme.sh")


def ensure_acme_sh() -> str:
    path = acme_sh_path()
    if os.path.isfile(path):
        return path
    print("Installing acme.sh for Cloudflare DNS-01 certificate issuance...")
    env = os.environ.copy()
    if os.geteuid() == 0:
        env["HOME"] = "/root"
    run_checked(
        ["bash", "-c", "curl -s https://get.acme.sh | sh"],
        env=env,
        timeout=300,
        error_message="Failed to install acme.sh",
    )
    if not os.path.isfile(path):
        exit_error("acme.sh installation completed but the executable was not found")
    return path


def issue_panel_certificate_with_cloudflare(
    *,
    domain: str,
    cf_token: str,
    zone_id: str,
) -> Tuple[str, str]:
    acme = ensure_acme_sh()
    cert_dir = f"/root/cert/{domain}"
    cert_file = f"{cert_dir}/fullchain.pem"
    key_file = f"{cert_dir}/privkey.pem"
    os.makedirs(cert_dir, exist_ok=True)

    env = os.environ.copy()
    if os.geteuid() == 0:
        env["HOME"] = "/root"
    env["CF_Token"] = cf_token
    env["CF_Zone_ID"] = zone_id
    env.pop("CF_Key", None)
    env.pop("CF_Email", None)

    run_checked(
        [acme, "--set-default-ca", "--server", "letsencrypt", "--force"],
        env=env,
        timeout=120,
        error_message="Failed to set the default acme.sh CA",
    )
    print(f"Issuing a Cloudflare DNS-01 certificate for 3x-ui panel domain {domain}...")
    run_checked(
        [acme, "--issue", "-d", domain, "--dns", "dns_cf", "--force"],
        env=env,
        timeout=600,
        error_message="Failed to issue panel certificate",
    )
    run_checked(
        [
            acme,
            "--installcert",
            "--force",
            "-d",
            domain,
            "--key-file",
            key_file,
            "--fullchain-file",
            cert_file,
            "--reloadcmd",
            "systemctl restart x-ui",
        ],
        env=env,
        timeout=180,
        error_message="Failed to install panel certificate",
    )
    try:
        os.chmod(key_file, 0o600)
        os.chmod(cert_file, 0o644)
    except OSError:
        pass
    return cert_file, key_file


def set_panel_certificate(cert_file: str, key_file: str) -> None:
    binary = find_xui_binary()
    if not binary:
        exit_error("x-ui binary not found; cannot configure panel certificate")
    run_checked(
        [binary, "cert", "-webCert", cert_file, "-webCertKey", key_file],
        timeout=30,
        error_message="Failed to configure 3x-ui panel certificate",
    )
    restart_xui_service()


def run_firewall_command(args: List[str], *, quiet: bool = False) -> bool:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if proc.returncode != 0:
        output = f"{proc.stdout or ''}\n{proc.stderr or ''}".strip()
        if output and not quiet:
            print(output[-1000:])
        return False
    return True


def ufw_is_active() -> bool:
    if not shutil.which("ufw"):
        return False
    try:
        status = subprocess.run(["ufw", "status"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "Status: active" in (status.stdout or "")


def firewalld_is_active() -> bool:
    if not shutil.which("firewall-cmd"):
        return False
    try:
        state = subprocess.run(
            ["firewall-cmd", "--state"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return state.returncode == 0 and "running" in (state.stdout or "")


def open_firewall_ports_if_active(ports: List[int]) -> None:
    unique_ports = sorted({int(p) for p in ports if int(p) > 0})
    opened = False
    if ufw_is_active():
        for port in unique_ports:
            run_firewall_command(["ufw", "allow", f"{port}/tcp"])
        print(f"Opened ports in UFW: {', '.join(map(str, unique_ports))}")
        opened = True

    if firewalld_is_active():
        for port in unique_ports:
            run_firewall_command(["firewall-cmd", "--permanent", "--add-port", f"{port}/tcp"])
        run_firewall_command(["firewall-cmd", "--reload"])
        print(f"Opened ports in firewalld: {', '.join(map(str, unique_ports))}")
        opened = True

    if not opened:
        print(
            "No active UFW/firewalld detected. Firewall auto-enable is skipped; "
            f"make sure the cloud security group allows: {', '.join(map(str, unique_ports))}/tcp"
        )


def fetch_text_lines(url: str, timeout: int = 10) -> List[str]:
    try:
        with request.urlopen(url, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return []
    return [item.strip() for item in text.split() if item.strip()]


def normalize_ip_ranges(ranges: List[str]) -> List[str]:
    valid_ranges: List[str] = []
    seen: Set[str] = set()
    for item in ranges:
        try:
            network = ipaddress.ip_network(item, strict=False)
        except ValueError:
            continue
        value = str(network)
        if value not in seen:
            valid_ranges.append(value)
            seen.add(value)
    return valid_ranges


def load_cached_cloudflare_ip_ranges() -> List[str]:
    try:
        with open(CF_IP_CACHE_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    ranges = payload.get("ranges")
    if not isinstance(ranges, list):
        return []
    return normalize_ip_ranges([str(item) for item in ranges])


def save_cached_cloudflare_ip_ranges(ranges: List[str]) -> None:
    try:
        parent = os.path.dirname(CF_IP_CACHE_PATH)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(CF_IP_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump({"updated_at": int(time.time()), "ranges": ranges}, f, indent=2)
        os.chmod(CF_IP_CACHE_PATH, 0o600)
    except OSError:
        return


def cloudflare_ip_ranges() -> Tuple[List[str], str]:
    live_ranges = normalize_ip_ranges(fetch_text_lines(CF_IPS_V4_URL) + fetch_text_lines(CF_IPS_V6_URL))
    if live_ranges:
        save_cached_cloudflare_ip_ranges(live_ranges)
        return live_ranges, "official"

    cached_ranges = load_cached_cloudflare_ip_ranges()
    if cached_ranges:
        return cached_ranges, "cache"

    fallback_ranges = normalize_ip_ranges(list(CF_FALLBACK_IP_RANGES))
    if fallback_ranges:
        return fallback_ranges, "fallback"

    return [], "none"


def normalize_ports(ports: List[int]) -> List[int]:
    normalized: List[int] = []
    for port in ports:
        try:
            value = int(port)
        except (TypeError, ValueError):
            continue
        if value > 0 and value not in normalized:
            normalized.append(value)
    return sorted(normalized)


def normalize_ports_value(value: Any) -> List[int]:
    return normalize_ports(value) if isinstance(value, list) else []


def normalize_ranges_value(value: Any) -> List[str]:
    return normalize_ip_ranges([str(x) for x in value]) if isinstance(value, list) else []


def firewall_rule_pairs(ports: List[int], ranges: List[str]) -> Set[Tuple[int, str]]:
    return {(int(port), str(ip_range)) for port in ports for ip_range in ranges}


def load_cloudflare_firewall_state() -> Dict[str, Any]:
    try:
        with open(CF_FIREWALL_STATE_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_cloudflare_firewall_state(state: Dict[str, Any]) -> None:
    try:
        parent = os.path.dirname(CF_FIREWALL_STATE_PATH)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(CF_FIREWALL_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.chmod(CF_FIREWALL_STATE_PATH, 0o600)
    except OSError as e:
        print(f"Failed to save Cloudflare firewall state: {e}")


def remove_cloudflare_firewall_state_if_empty(state: Dict[str, Any]) -> None:
    has_rules = cloudflare_firewall_state_has_rules(state)
    if has_rules or normalize_ports_value(state.get("ports")):
        save_cloudflare_firewall_state(state)
        return
    try:
        if os.path.exists(CF_FIREWALL_STATE_PATH):
            os.remove(CF_FIREWALL_STATE_PATH)
    except OSError:
        return


def cloudflare_firewall_state_has_rules(state: Dict[str, Any]) -> bool:
    backends = state.get("backends") if isinstance(state.get("backends"), dict) else {}
    for item in backends.values():
        if not isinstance(item, dict):
            continue
        ports = normalize_ports_value(item.get("ports"))
        ranges = normalize_ranges_value(item.get("ranges"))
        if ports and ranges:
            return True
    return False


def backend_state_pairs(state: Dict[str, Any], backend: str) -> Set[Tuple[int, str]]:
    backends = state.get("backends")
    if not isinstance(backends, dict):
        return set()
    item = backends.get(backend)
    if not isinstance(item, dict):
        return set()
    ports = normalize_ports_value(item.get("ports"))
    ranges = normalize_ranges_value(item.get("ranges"))
    return firewall_rule_pairs(ports, ranges)


def set_backend_state(state: Dict[str, Any], backend: str, pairs: Set[Tuple[int, str]]) -> None:
    backends = state.setdefault("backends", {})
    if not isinstance(backends, dict):
        backends = {}
        state["backends"] = backends
    ports = sorted({port for port, _ in pairs})
    ranges = normalize_ip_ranges([ip_range for _, ip_range in sorted(pairs)])
    if ports and ranges:
        backends[backend] = {"ports": ports, "ranges": ranges}
    elif backend in backends:
        del backends[backend]


def active_cloudflare_firewall_backends() -> List[str]:
    backends: List[str] = []
    if ufw_is_active():
        backends.append("ufw")
    if firewalld_is_active():
        backends.append("firewalld")
    return backends


def ufw_rule_command(action: str, port: int, ip_range: str) -> List[str]:
    base = ["ufw"]
    if action == "delete":
        base.append("delete")
    base.extend(["allow", "proto", "tcp", "from", ip_range, "to", "any", "port", str(port)])
    return base


def firewalld_rich_rule(port: int, ip_range: str) -> str:
    family = "ipv6" if ":" in ip_range else "ipv4"
    return f"rule family={family} source address={ip_range} port port={port} protocol=tcp accept"


def firewalld_rule_command(action: str, port: int, ip_range: str) -> List[str]:
    flag = "--remove-rich-rule" if action == "delete" else "--add-rich-rule"
    return ["firewall-cmd", "--permanent", flag, firewalld_rich_rule(port, ip_range)]


def apply_cloudflare_firewall_backend(
    backend: str,
    current_pairs: Set[Tuple[int, str]],
    desired_pairs: Set[Tuple[int, str]],
) -> Set[Tuple[int, str]]:
    to_delete = sorted(current_pairs - desired_pairs)
    to_add = sorted(desired_pairs - current_pairs)
    applied_pairs = set(current_pairs)

    for port, ip_range in to_delete:
        if backend == "ufw":
            run_firewall_command(ufw_rule_command("delete", port, ip_range), quiet=True)
        else:
            run_firewall_command(firewalld_rule_command("delete", port, ip_range), quiet=True)
        applied_pairs.discard((port, ip_range))

    for port, ip_range in to_add:
        if backend == "ufw":
            ok = run_firewall_command(ufw_rule_command("add", port, ip_range))
        else:
            ok = run_firewall_command(firewalld_rule_command("add", port, ip_range))
        if ok:
            applied_pairs.add((port, ip_range))

    if backend == "firewalld" and (to_add or to_delete):
        run_firewall_command(["firewall-cmd", "--reload"])
    return applied_pairs


def sync_cloudflare_origin_firewall_ports(ports: List[int]) -> None:
    desired_ports = normalize_ports(ports)
    state = load_cloudflare_firewall_state()
    ranges, source = cloudflare_ip_ranges()
    previous_ranges = normalize_ranges_value(state.get("ranges"))

    if source == "fallback" and previous_ranges:
        ranges = previous_ranges
        source = "state"
    if not ranges and previous_ranges:
        ranges = previous_ranges
        source = "state"

    if not ranges:
        print(
            "Could not load Cloudflare IP ranges. Node port firewall rules were not changed; "
            f"make sure Cloudflare can reach: {', '.join(map(str, desired_ports))}/tcp"
        )
        return
    if source == "fallback":
        print(
            "Using bundled fallback Cloudflare IP ranges because the official list and local cache were unavailable. "
            "Review firewall rules after network access is restored."
        )

    desired_pairs = firewall_rule_pairs(desired_ports, ranges)
    active_backends = active_cloudflare_firewall_backends()
    if not active_backends:
        state["version"] = 1
        state["ports"] = desired_ports
        state["ranges"] = ranges
        state["updated_at"] = int(time.time())
        remove_cloudflare_firewall_state_if_empty(state)
        print(
            "No active UFW/firewalld detected. Firewall auto-enable is skipped; "
            f"make sure the cloud security group allows Cloudflare to reach: {', '.join(map(str, desired_ports))}/tcp"
        )
        return

    for backend in active_backends:
        current_pairs = backend_state_pairs(state, backend)
        next_pairs = apply_cloudflare_firewall_backend(backend, current_pairs, desired_pairs)
        set_backend_state(state, backend, next_pairs)
        added = len(next_pairs - current_pairs)
        removed = len(current_pairs - next_pairs)
        print(f"Synced Cloudflare firewall rules for {backend}: added {added}, removed {removed}")

    state["version"] = 1
    state["ports"] = desired_ports
    state["ranges"] = ranges
    state["updated_at"] = int(time.time())
    remove_cloudflare_firewall_state_if_empty(state)


def open_cloudflare_origin_ports_if_active(ports: List[int]) -> None:
    sync_cloudflare_origin_firewall_ports(ports)


def node_ports_from_deployment_state(state: Optional[Dict[str, Any]]) -> List[int]:
    if not isinstance(state, dict):
        return []
    routes = state.get("routes")
    if not isinstance(routes, list):
        return []
    ports: List[int] = []
    for route in routes:
        if not isinstance(route, dict):
            continue
        try:
            ports.append(int(route.get("port", 0)))
        except (TypeError, ValueError):
            continue
    return normalize_ports(ports)


def sync_cloudflare_firewall_from_state() -> None:
    firewall_state = load_cloudflare_firewall_state()
    ports = normalize_ports_value(firewall_state.get("ports"))
    if not ports:
        if cloudflare_firewall_state_has_rules(firewall_state):
            sync_cloudflare_origin_firewall_ports([])
            return
        ports = node_ports_from_deployment_state(load_last_state())
    if not ports:
        print("No managed node ports found for Cloudflare firewall sync")
        return
    sync_cloudflare_origin_firewall_ports(ports)


def write_text_if_changed(path: str, content: str, mode: int = 0o644) -> bool:
    try:
        current = ""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                current = f.read()
        if current == content:
            return False
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(path, mode)
        return True
    except OSError:
        return False


def systemd_available() -> bool:
    return os.geteuid() == 0 and shutil.which("systemctl") is not None and os.path.isdir("/run/systemd/system")


def run_systemctl(args: List[str]) -> bool:
    try:
        proc = subprocess.run(["systemctl"] + args, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if proc.returncode != 0:
        output = f"{proc.stdout or ''}\n{proc.stderr or ''}".strip()
        if output:
            print(output[-1000:])
        return False
    return True


def ensure_cloudflare_firewall_timer() -> None:
    if not systemd_available():
        return
    python_path = shutil.which("python3") or sys.executable or "/usr/bin/python3"
    service_content = (
        "[Unit]\n"
        "Description=Sync 3x-ui Cloudflare origin firewall rules\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"ExecStart={python_path} {DEPLOYER_INSTALL_PATH} --sync-cloudflare-firewall\n"
    )
    timer_content = (
        "[Unit]\n"
        "Description=Run 3x-ui Cloudflare origin firewall sync periodically\n"
        "\n"
        "[Timer]\n"
        "OnBootSec=5min\n"
        "OnUnitActiveSec=6h\n"
        "RandomizedDelaySec=15min\n"
        "Persistent=true\n"
        "\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )
    changed = False
    changed = write_text_if_changed(CF_FIREWALL_SERVICE_PATH, service_content) or changed
    changed = write_text_if_changed(CF_FIREWALL_TIMER_PATH, timer_content) or changed
    if changed:
        run_systemctl(["daemon-reload"])
    if run_systemctl(["enable", "--now", CF_FIREWALL_TIMER]):
        print(f"Cloudflare firewall sync timer enabled: {CF_FIREWALL_TIMER}")


def read_panel_user_from_db() -> Tuple[str, str]:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("SELECT username, password FROM users ORDER BY id LIMIT 1")
            row = cur.fetchone()
    except sqlite3.Error as e:
        exit_error(str(e))
    if not row or not row[0]:
        exit_error("Panel login account was not found. Install 3x-ui first.")
    return str(row[0]), str(row[1] or "")


def collect_panel_access_info(
    *,
    installed_by_script: bool = False,
    plain_username: Optional[str] = None,
    plain_password: Optional[str] = None,
    panel_domain: Optional[str] = None,
) -> Dict[str, Any]:
    binary = find_xui_binary()
    db_username, db_password = read_panel_user_from_db()
    username = plain_username or db_username
    password = plain_password or db_password
    if is_password_hash(password):
        exit_error("Cannot read the panel plaintext password. Run fresh install mode again.")
    port_text = read_setting_from_db("webPort") or "2053"
    base_path = read_setting_from_db("webBasePath") or "/"
    listen_ip = (read_setting_from_db("listenIP") or "").strip()
    cert = (read_setting_from_db("webCertFile") or "").strip()
    key = (read_setting_from_db("webKeyFile") or "").strip()
    https = bool(cert and key)
    scheme = "https" if https else "http"
    if not base_path.startswith("/"):
        base_path = f"/{base_path}"
    base_path = base_path.rstrip("/") or ""
    path_suffix = base_path if base_path else ""
    try:
        port = int(port_text)
    except ValueError:
        port = 2053
    local_host = "127.0.0.1"
    if listen_ip in ("127.0.0.1", "::1", "localhost"):
        local_host = "127.0.0.1"
    local_url = f"{scheme}://{local_host}:{port}{path_suffix}"
    domain_url = ""
    if panel_domain:
        domain_url = f"https://{normalize_domain(panel_domain)}:{port}{path_suffix}"
    public_url = ""
    if listen_ip not in ("127.0.0.1", "::1", "localhost"):
        try:
            public_ip = get_public_ipv4()
            public_url = f"{scheme}://{public_ip}:{port}{path_suffix}"
        except SystemExit:
            public_url = ""
    api_token = read_api_token_from_cli(binary) or os.environ.get("XUI_API_TOKEN", "").strip()
    info: Dict[str, Any] = {
        "username": username,
        "password": password,
        "port": port,
        "web_base_path": base_path or "/",
        "listen_ip": listen_ip,
        "access_url_local": local_url,
        "access_url_domain": domain_url,
        "panel_domain": normalize_domain(panel_domain) if panel_domain else "",
        "access_url_public": public_url,
        "api_token": api_token,
        "installed_at": int(time.time()),
    }
    if installed_by_script:
        info["installed_by_script"] = True
    return info


def save_panel_access_info(info: Dict[str, Any]) -> None:
    try:
        with open(PANEL_INFO_PATH, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
        os.chmod(PANEL_INFO_PATH, 0o600)
    except OSError as e:
        exit_error(f"Failed to save panel access info: {e}")

    lines = [
        "3x-ui panel access info",
        f"Username: {info.get('username', '')}",
        f"Password: {info.get('password', '')}",
        f"Local URL: {info.get('access_url_local', '')}",
    ]
    domain_url = str(info.get("access_url_domain") or "").strip()
    if domain_url:
        lines.append(f"Bound domain: {domain_url}")
    public_url = str(info.get("access_url_public") or "").strip()
    if public_url:
        lines.append(f"Public URL: {public_url}")
    api_token = str(info.get("api_token") or "").strip()
    if api_token:
        lines.append(f"API Token: {api_token}")
    lines.append("")
    try:
        with open(PANEL_INFO_SNAPSHOT, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except OSError as e:
        exit_error(f"Failed to save panel snapshot: {e}")


def load_panel_access_record() -> Optional[Dict[str, Any]]:
    if not os.path.isfile(PANEL_INFO_PATH):
        return None
    try:
        with open(PANEL_INFO_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def has_script_installed_panel() -> bool:
    info = load_panel_access_record()
    return bool(info and info.get("installed_by_script"))


def load_panel_access_info() -> Optional[Dict[str, Any]]:
    return load_panel_access_record()


def print_panel_access_info() -> None:
    if not has_script_installed_panel():
        exit_error("This panel was not installed by this script; panel access info is unavailable")

    if os.path.isfile(PANEL_INFO_SNAPSHOT):
        try:
            with open(PANEL_INFO_SNAPSHOT, "r", encoding="utf-8") as f:
                content = f.read().strip()
        except OSError as e:
            exit_error(f"Failed to read panel access info: {e}")
        if content:
            print(content)
            return

    info = load_panel_access_info()
    if not info:
        exit_error("Panel access info was not found. Run fresh install mode first.")
    exit_error("Panel access snapshot was not found. Run fresh install mode again.")


def ensure_xui_for_fresh_setup(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if is_xui_installed():
        exit_error("Detected an existing 3x-ui installation. Use mode 1 to deploy nodes.")
    panel_domain = str(context.get("panel_domain") or "").strip()
    panel_port = choose_cloudflare_panel_port() if panel_domain else None
    panel_config = None
    if panel_domain and panel_port:
        panel_config = prepare_panel_cloudflare(context=context, panel_port=panel_port)
    username, password = run_xui_install_script(panel_port=panel_port)
    if panel_domain:
        install_panel_cloudflare_certificate(context)
    info = collect_panel_access_info(
        installed_by_script=True,
        plain_username=username,
        plain_password=password,
        panel_domain=panel_domain or None,
    )
    save_panel_access_info(info)
    print(f"Panel info saved to {PANEL_INFO_SNAPSHOT}")
    print(f"Local URL: {info['access_url_local']}")
    if info.get("access_url_domain"):
        print(f"Bound domain: {info['access_url_domain']}")
    print(f"Username: {info['username']}")
    print(f"Password: {info['password']}")
    return panel_config


def ensure_cfd_command() -> bool:
    if os.geteuid() != 0:
        return False
    script_path = os.path.realpath(__file__)
    install_dir = os.path.dirname(DEPLOYER_INSTALL_PATH)
    try:
        os.makedirs(install_dir, exist_ok=True)
        need_copy = True
        if os.path.isfile(DEPLOYER_INSTALL_PATH):
            try:
                need_copy = os.path.getsize(script_path) != os.path.getsize(DEPLOYER_INSTALL_PATH)
            except OSError:
                need_copy = True
        if need_copy:
            shutil.copy2(script_path, DEPLOYER_INSTALL_PATH)
        os.chmod(DEPLOYER_INSTALL_PATH, 0o755)

        first_install = not os.path.isfile(CFD_BIN)
        cfd_script = (
            "#!/bin/bash\n"
            f"exec python3 {DEPLOYER_INSTALL_PATH} \"$@\"\n"
        )
        with open(CFD_BIN, "w", encoding="utf-8") as f:
            f.write(cfd_script)
        os.chmod(CFD_BIN, 0o755)
        if first_install:
            print(f"Registered shortcut command cfd. Run cfd later to open this script.")
        ensure_cloudflare_firewall_timer()
        return True
    except OSError:
        return False


def print_xui_management_help() -> None:
    if not is_xui_installed():
        exit_error("3x-ui is not installed. Management commands are unavailable.")

    lines = [
        "3x-ui management commands",
        "",
        "To manage the panel later, run:",
        "  x-ui",
        "",
        "Common commands you can run directly without opening the menu:",
        "  x-ui start              Start panel",
        "  x-ui stop               Stop panel",
        "  x-ui restart            Restart panel",
        "  x-ui restart-xray       Restart Xray",
        "  x-ui status             Show status",
        "  x-ui settings           Show current panel settings",
        "  x-ui enable             Enable autostart",
        "  x-ui disable            Disable autostart",
        "  x-ui log                Show logs",
        "  x-ui update             Update 3x-ui",
        "",
        "CF deployer shortcut command:",
        "  cfd                     Open this script again",
        "",
        "After opening the x-ui interactive menu, you can change ports, reset passwords, manage SSL certificates, and more.",
        "",
        "Tip: run x-ui any time to open the 3x-ui management menu",
    ]
    if shutil.which("cfd"):
        lines.append("Tip: run cfd any time to open this deployer")
    print("\n".join(lines))


def build_mode_menu_items() -> List[Tuple[str, str]]:
    items: List[Tuple[str, str]] = [
        ("install", "Deploy nodes"),
        ("uninstall", "Uninstall"),
        ("show", "Show subscriptions"),
    ]
    if not is_xui_installed():
        items.append(("fresh", "Fresh install (with x-ui)"))
    if has_script_installed_panel():
        items.append(("panel", "Show panel"))
    if is_xui_installed():
        items.append(("xui_manage", "Panel management commands"))
    return items


def default_mode_index(items: List[Tuple[str, str]]) -> int:
    preferred = "fresh" if not is_xui_installed() else "install"
    for i, (mode_id, _) in enumerate(items):
        if mode_id == preferred:
            return i
    return 0


def parse_mode(raw: str, items: Optional[List[Tuple[str, str]]] = None) -> str:
    menu = items or build_mode_menu_items()
    text = raw.strip().lower()
    if text == "":
        return menu[default_mode_index(menu)][0]
    if text.isdigit():
        idx = int(text) - 1
        if 0 <= idx < len(menu):
            return menu[idx][0]
    aliases = {
        "install": "install",
        "i": "install",
        "deploy": "install",
        "uninstall": "uninstall",
        "u": "uninstall",
        "Uninstall": "uninstall",
        "show": "show",
        "view": "show",
        "v": "show",
        "view-links": "show",
        "Show subscriptions": "show",
        "fresh": "fresh",
        "setup": "fresh",
        "new": "fresh",
        "fresh-install": "fresh",
        "install-x-ui": "fresh",
        "panel": "panel",
        "panel-info": "panel",
        "Show panel": "panel",
        "xui": "xui_manage",
        "manage": "xui_manage",
        "commands": "xui_manage",
        "management-commands": "xui_manage",
        "panel-management": "xui_manage",
    }
    mode_id = aliases.get(text)
    if mode_id and any(item[0] == mode_id for item in menu):
        return mode_id
    valid = " / ".join(str(i + 1) for i in range(len(menu)))
    exit_error(f"Invalid mode. Enter {valid}")


def _read_nav_key() -> str:
    if not HAS_TERMIOS:
        return "enter"
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch in ("\r", "\n"):
                return "enter"
            if ch == "\x03":
                raise KeyboardInterrupt
            if ch == "\x1b":
                seq = sys.stdin.read(2)
                if seq == "[A":
                    return "up"
                if seq == "[B":
                    return "down"
                if seq == "[C":
                    return "right"
                if seq == "[D":
                    return "left"
                continue
            if ch in ("k", "K", "w", "W"):
                return "up"
            if ch in ("j", "J", "s", "S"):
                return "down"
            if ch in ("h", "H", "a", "A"):
                return "left"
            if ch in ("l", "L", "d", "D"):
                return "right"
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _mode_menu_line_count(items: List[Tuple[str, str]]) -> int:
    # title + blank line + options + blank line + footer
    return 2 + len(items) + 2


def _render_mode_menu(items: List[Tuple[str, str]], index: int, *, redraw: bool) -> None:
    if redraw:
        sys.stdout.write(f"\033[{_mode_menu_line_count(items)}A")

    lines = [
        "Select mode (arrow keys / WASD / HJKL to move, Enter to confirm):",
        "",
    ]
    for i, (_, label) in enumerate(items):
        if i == index:
            lines.append(f"  \033[1;36m> {label}\033[0m")
        else:
            lines.append(f"    {label}")
    lines.extend(["", "Move with arrow keys, WASD, or HJKL. Press Enter to confirm."])

    for line in lines:
        sys.stdout.write("\033[2K\r")
        sys.stdout.write(f"{line}\n")
    sys.stdout.flush()


def select_mode_plain(items: List[Tuple[str, str]]) -> str:
    default_idx = default_mode_index(items)
    print("Select mode:")
    for i, (_, label) in enumerate(items, 1):
        marker = " (default)" if i - 1 == default_idx else ""
        print(f"  {i}. {label}{marker}")
    raw = input(f"Enter number (Enter={items[default_idx][1]}): ")
    return parse_mode(raw, items)


def select_mode_cursor(items: List[Tuple[str, str]]) -> str:
    index = default_mode_index(items)
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()
    _render_mode_menu(items, index, redraw=False)
    while True:
        key = _read_nav_key()
        if key in ("up", "left"):
            index = (index - 1) % len(items)
            _render_mode_menu(items, index, redraw=True)
            continue
        if key in ("down", "right"):
            index = (index + 1) % len(items)
            _render_mode_menu(items, index, redraw=True)
            continue
        if key == "enter":
            sys.stdout.write("\033[?25h\n")
            sys.stdout.flush()
            return items[index][0]


def select_mode_interactive() -> str:
    items = build_mode_menu_items()
    if not items:
        exit_error("No available mode")
    use_plain = (
        not sys.stdin.isatty()
        or not HAS_TERMIOS
        or os.environ.get("CFD_PLAIN_MENU", "").strip().lower() in ("1", "true", "yes", "y")
    )
    if use_plain:
        return select_mode_plain(items)
    try:
        return select_mode_cursor(items)
    except KeyboardInterrupt:
        sys.stdout.write("\033[?25h\n")
        sys.stdout.flush()
        print("Cancelled")
        sys.exit(130)


def panel_tls_insecure(panel_url: str, panel_https: bool) -> bool:
    if not panel_https:
        return False
    if os.environ.get("XUI_TLS_INSECURE", "").strip().lower() in ("1", "true", "yes", "y"):
        return True
    host = parse.urlparse(panel_url).hostname or ""
    return host in ("127.0.0.1", "localhost", "::1")


def probe_panel_api(panel_url: str, api_token: Optional[str], insecure_tls: bool) -> bool:
    client = XuiPanelClient(panel_url, token=api_token, insecure_tls=insecure_tls)
    csrf = call_json_api(
        "GET",
        client._url("csrf-token"),
        headers=client._headers(),
        opener=client.opener,
        exit_on_http_error=False,
        timeout=8,
    )
    if csrf.get("success") and isinstance(csrf.get("obj"), str):
        return True
    if api_token:
        listed = call_json_api(
            "GET",
            client._url(f"{PANEL_API_PREFIX}/inbounds/list"),
            headers=client._headers(),
            opener=client.opener,
            exit_on_http_error=False,
            timeout=8,
        )
        return bool(listed.get("success"))
    return False


def api_auth_available(env: Dict[str, Any]) -> bool:
    return bool((env.get("api_token") or "").strip())


def find_xui_cli_script() -> Optional[str]:
    candidates: List[str] = []
    which = shutil.which("x-ui")
    if which:
        candidates.append(which)
    candidates.extend(XUI_CLI_SCRIPT_CANDIDATES)

    seen: Set[str] = set()
    for path in candidates:
        if not path or path in seen or not os.path.isfile(path):
            continue
        seen.add(path)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                head = handle.read(4096)
        except OSError:
            continue
        if "show_menu()" in head or "Panel Management Script" in head:
            return path
    return None


def is_xui_menu_localized(script_path: str) -> bool:
    try:
        with open(script_path, "r", encoding="utf-8", errors="ignore") as handle:
            return XUI_MENU_ZH_MARKER in handle.read(8192)
    except OSError:
        return False


def apply_xui_menu_localization() -> None:
    script_path = find_xui_cli_script()
    if not script_path:
        print("x-ui command script not found. Skipping localization.")
        return
    if is_xui_menu_localized(script_path):
        print("x-ui command menu is already localized. Skipping.")
        return

    try:
        with open(script_path, "r", encoding="utf-8", errors="ignore") as handle:
            content = handle.read()
    except OSError as e:
        exit_error(f"Failed to read x-ui script: {e}")

    backup_path = f"{script_path}.en.bak"
    if not os.path.exists(backup_path):
        try:
            shutil.copy2(script_path, backup_path)
        except OSError as e:
            exit_error(f"Failed to back up x-ui script: {e}")

    updated = content
    applied = 0
    for old, new in XUI_MENU_REPLACEMENTS:
        if old not in updated:
            continue
        updated = updated.replace(old, new)
        applied += 1

    if applied == 0:
        exit_error("x-ui localization failed: no matching menu text was found. The script version may be incompatible.")

    if updated.startswith("#!"):
        lines = updated.splitlines(keepends=True)
        if not any(XUI_MENU_ZH_MARKER in line for line in lines[:5]):
            lines.insert(1, f"{XUI_MENU_ZH_MARKER}\n")
        updated = "".join(lines)
    else:
        updated = f"{XUI_MENU_ZH_MARKER}\n{updated}"

    try:
        with open(script_path, "w", encoding="utf-8") as handle:
            handle.write(updated)
    except OSError as e:
        exit_error(f"Failed to write localized x-ui script: {e}")

    print(f"x-ui command menu localized: {script_path}")
    print(f"English backup: {backup_path}")


def prompt_maybe_localize_xui_menu() -> None:
    env_flag = os.environ.get("XUI_LOCALIZE_MENU", "").strip().lower()
    if env_flag in ("0", "no", "n", "false"):
        return
    if env_flag in ("1", "yes", "y", "true"):
        apply_xui_menu_localization()
        return

    script_path = find_xui_cli_script()
    if not script_path or is_xui_menu_localized(script_path):
        return

    answer = input("Localize x-ui command menu? (y/N): ").strip().lower()
    if answer in ("y", "yes"):
        apply_xui_menu_localization()


def detect_xui_environment() -> Dict[str, Any]:
    binary = find_xui_binary()
    version = read_xui_version(binary)
    version_tuple = parse_version(version) if version else (0,)
    db_available = os.path.isfile(DB_PATH)
    panel_url, panel_https = detect_panel_url()
    insecure_tls = panel_tls_insecure(panel_url, panel_https)
    api_token = os.environ.get("XUI_API_TOKEN", "").strip() or read_api_token_from_cli(binary)

    api_capable = version_tuple == (0,) or version_at_least(version_tuple, API_MIN_VERSION)
    api_reachable = False
    if api_capable:
        api_reachable = probe_panel_api(panel_url, api_token, insecure_tls)

    return {
        "binary": binary,
        "version": version,
        "version_tuple": version_tuple,
        "db_available": db_available,
        "panel_url": panel_url,
        "panel_https": panel_https,
        "insecure_tls": insecure_tls,
        "api_token": api_token,
        "api_capable": api_capable,
        "api_reachable": api_reachable,
    }


def backend_label(backend: str) -> str:
    return "API" if backend == BACKEND_API else "direct SQLite"


def auto_select_backend(
    env: Dict[str, Any],
    state: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    explicit = os.environ.get("XUI_BACKEND", "").strip().lower()
    if explicit == BACKEND_DB:
        return BACKEND_DB, "environment variable XUI_BACKEND=db"
    if explicit == BACKEND_API:
        if not api_auth_available(env):
            exit_error("API mode was forced but no API Token was detected")
        return BACKEND_API, "environment variable XUI_BACKEND=api"

    from_state = backend_from_state(state)
    if from_state:
        return from_state, "state file record"

    if api_auth_available(env):
        return BACKEND_API, "API Token detected, using API"

    if env.get("db_available"):
        return BACKEND_DB, "API Token not detected, using direct SQLite"

    exit_error("API Token was not detected and the local database does not exist")


def resolve_backend(
    state: Optional[Dict[str, Any]] = None,
    env: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any], str]:
    runtime = env or detect_xui_environment()
    backend, reason = auto_select_backend(runtime, state)
    return backend, runtime, reason


def setup_panel_client(env: Dict[str, Any], *, interactive: bool = True) -> XuiPanelClient:
    panel_url = os.environ.get("XUI_PANEL_URL", "").strip() or str(env["panel_url"])
    insecure = bool(env.get("insecure_tls"))
    token = os.environ.get("XUI_API_TOKEN", "").strip() or str(env.get("api_token") or "").strip()
    if not token:
        exit_error("API mode requires an API Token. Get it with x-ui setting -getApiToken.")
    return XuiPanelClient(panel_url, token=token, insecure_tls=insecure)


def backend_from_state(state: Optional[Dict[str, Any]]) -> Optional[str]:
    if not state:
        return None
    backend = str(state.get("backend", "")).strip().lower()
    if backend in (BACKEND_DB, BACKEND_API):
        return backend
    version = state.get("version")
    if version == 2:
        return BACKEND_API
    if version == 1:
        return BACKEND_DB
    return None


def prompt_panel_client() -> XuiPanelClient:
    panel_url = (
        os.environ.get("XUI_PANEL_URL", "").strip()
        or input(f"3x-ui panel URL(Enter={DEFAULT_PANEL_URL}): ").strip()
        or DEFAULT_PANEL_URL
    )
    insecure = panel_url.lower().startswith("https://")
    if insecure:
        answer = input("Panel uses HTTPS and may have a self-signed certificate. Skip certificate verification? (Y/n): ").strip().lower()
        insecure = answer in ("", "y", "yes")

    token = os.environ.get("XUI_API_TOKEN", "").strip()
    if not token:
        auth_mode = input("3x-ui auth(1=username/password,2=API Token, Enter=1): ").strip() or "1"
        if auth_mode in ("2", "token", "t"):
            token = getpass("3x-ui API Token: ").strip()
            if not token:
                exit_error("API Token cannot be empty")
            return XuiPanelClient(panel_url, token=token, insecure_tls=insecure)

    username = os.environ.get("XUI_USERNAME", "").strip()
    password = os.environ.get("XUI_PASSWORD", "").strip()
    if not username:
        username = input("3x-ui Username: ").strip()
    if not password:
        password = getpass("3x-ui Password: ").strip()
    if not username or not password:
        exit_error("3x-ui username and password cannot be empty")

    client = XuiPanelClient(panel_url, insecure_tls=insecure)
    two_factor = os.environ.get("XUI_2FA", "").strip()
    if not two_factor and not sys.stdin.isatty():
        two_factor = ""
    elif not two_factor:
        two_factor = input("3x-ui two-factor code(Enter if none): ").strip()
    client.login(username, password, two_factor_code=two_factor)
    return client


def get_public_ipv4() -> str:
    providers = [
        "https://api.ipify.org",
        "https://ipv4.icanhazip.com",
        "https://ifconfig.me/ip",
    ]
    for url in providers:
        try:
            with request.urlopen(url, timeout=8) as resp:
                ip_text = resp.read().decode("utf-8").strip()
            ipaddress.IPv4Address(ip_text)
            return ip_text
        except error.HTTPError as e:
            print(e.read().decode("utf-8", errors="ignore"))
            sys.exit(1)
        except Exception:
            continue
    exit_error("Failed to get public IPv4")


def find_best_zone(domain: str, zones: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    input_domain = domain.strip(".").lower()
    best_match = None
    for zone in zones:
        zone_name = str(zone.get("name", "")).strip(".").lower()
        if not zone_name:
            continue
        if input_domain == zone_name or input_domain.endswith(f".{zone_name}"):
            if best_match is None or len(zone_name) > len(best_match["name"]):
                best_match = zone
    return best_match


def fetch_all_zones(headers: Dict[str, str]) -> List[Dict[str, Any]]:
    page = 1
    zones: List[Dict[str, Any]] = []
    while True:
        endpoint = f"/zones?per_page=100&page={page}"
        result = call_json_api("GET", f"{CF_API_BASE}{endpoint}", headers=headers)
        if not result.get("success", False):
            errors = result.get("errors") or [{"message": "Failed to fetch Zone list"}]
            print(json.dumps(errors, ensure_ascii=False))
            sys.exit(1)
        zones.extend(result.get("result", []))
        info = result.get("result_info") or {}
        total_pages = int(info.get("total_pages") or 1)
        if page >= total_pages:
            break
        page += 1
    return zones


def get_dns_record(zone_id: str, domain: str, headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
    q = parse.urlencode({"type": "A", "name": domain})
    existing = call_cf_api("GET", f"/zones/{zone_id}/dns_records?{q}", headers=headers)
    if existing:
        return existing[0]
    return None


def upsert_dns_record(zone_id: str, domain: str, ip: str, headers: Dict[str, str]) -> str:
    existing = get_dns_record(zone_id, domain, headers)
    payload = {
        "type": "A",
        "name": domain,
        "content": ip,
        "proxied": True,
        "ttl": 1,
    }
    if existing:
        record_id = str(existing["id"])
        call_cf_api("PUT", f"/zones/{zone_id}/dns_records/{record_id}", headers=headers, data=payload)
        return record_id
    created = call_cf_api("POST", f"/zones/{zone_id}/dns_records", headers=headers, data=payload)
    return str(created["id"])


def prompt_panel_domain(
    *,
    node_domain: str,
    zone_name: str,
    zone_id: str,
    zones: List[Dict[str, Any]],
) -> str:
    default_domain = default_panel_domain_for(node_domain, zone_name)
    raw = input(f"3x-ui panel domain(Enter={default_domain}, type skip to skip): ").strip()
    if raw.lower() in ("skip", "none", "no", "n"):
        return ""
    panel_domain = normalize_domain(raw or default_domain)
    if panel_domain == normalize_domain(node_domain):
        exit_error("Panel domain cannot equal node domain because node flexible and panel strict would conflict")
    panel_zone = find_best_zone(panel_domain, zones)
    if not panel_zone or str(panel_zone.get("id", "")) != zone_id:
        exit_error("Panel domain must belong to the same Cloudflare Zone")
    return panel_domain


def prompt_deploy_context() -> Dict[str, Any]:
    deployer_cf_url = current_deployer_cf_url()
    domain = normalize_domain(input("Node domain: ").strip())
    cf_token = prompt_cf_api_token()
    selected_protocols = parse_protocol_selection(
        input("Protocols(1=vless,2=trojan,3=vmess, comma-separated, empty=all): ")
    )

    if not cf_token or not selected_protocols:
        exit_error("API Token and protocol selection cannot be empty")

    headers = build_cf_headers(cf_token)
    zones = fetch_all_zones(headers)
    zone = find_best_zone(domain, zones)
    if zone is None:
        exit_error(f"Could not match a Cloudflare Zone for this domain: {domain}")

    zone_id = str(zone["id"])
    zone_name = str(zone["name"])
    panel_domain = prompt_panel_domain(
        node_domain=domain,
        zone_name=zone_name,
        zone_id=zone_id,
        zones=zones,
    )
    public_ip = get_public_ipv4()
    return {
        "deployer_cf_url": deployer_cf_url,
        "domain": domain,
        "cf_token": cf_token,
        "headers": headers,
        "zones": zones,
        "zone": zone,
        "zone_id": zone_id,
        "zone_name": zone_name,
        "panel_domain": panel_domain,
        "public_ip": public_ip,
        "selected_protocols": selected_protocols,
    }


def prepare_panel_cloudflare(
    *,
    context: Dict[str, Any],
    panel_port: int,
) -> Optional[Dict[str, Any]]:
    panel_domain = str(context.get("panel_domain") or "").strip()
    if not panel_domain:
        return None
    zone_id = str(context["zone_id"])
    headers = context["headers"]
    public_ip = str(context["public_ip"])

    dns_before = get_dns_record(zone_id, panel_domain, headers)
    record_id = upsert_dns_record(zone_id, panel_domain, public_ip, headers)
    apply_ssl_config_rules(zone_id, headers, [(panel_domain, "strict", "panel")])
    open_firewall_ports_if_active(FIREWALL_PANEL_PORTS + [panel_port])
    print(f"Configured 3x-ui panel domain: https://{panel_domain}:{panel_port}")
    return {
        "domain": panel_domain,
        "port": panel_port,
        "managed_dns_record_id": record_id,
        "dns_backup": {
            "existed": dns_before is not None,
            "record": dns_before,
        },
        "ssl_config_mode": "strict",
    }


def install_panel_cloudflare_certificate(context: Dict[str, Any]) -> None:
    panel_domain = str(context.get("panel_domain") or "").strip()
    if not panel_domain:
        return
    cert_file, key_file = issue_panel_certificate_with_cloudflare(
        domain=panel_domain,
        cf_token=str(context["cf_token"]),
        zone_id=str(context["zone_id"]),
    )
    set_panel_certificate(cert_file, key_file)
    print(f"3x-ui panel certificate enabled: {cert_file}")


def configure_existing_panel_cloudflare(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    panel_domain = str(context.get("panel_domain") or "").strip()
    if not panel_domain:
        return None
    panel_port = ensure_cloudflare_panel_port()
    panel_config = prepare_panel_cloudflare(context=context, panel_port=panel_port)
    install_panel_cloudflare_certificate(context)
    print(f"3x-ui panel URL: {panel_url_for_domain(panel_domain, panel_port)}")
    return panel_config


def get_ssl_mode(zone_id: str, headers: Dict[str, str]) -> str:
    result = call_cf_api("GET", f"/zones/{zone_id}/settings/ssl", headers=headers)
    value = str(result.get("value", "")).strip()
    if not value:
        exit_error("Failed to read Cloudflare SSL mode")
    return value


def set_ssl_mode(zone_id: str, headers: Dict[str, str], mode: str) -> None:
    call_cf_api(
        "PATCH",
        f"/zones/{zone_id}/settings/ssl",
        headers=headers,
        data={"value": mode},
    )


def build_origin_rules(domain: str, routes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rules = []
    host = domain.strip().lower()
    for route in routes:
        rules.append(
            {
                "description": f"{MANAGED_RULE_PREFIX}{route['protocol']} {route['path']}",
                "enabled": True,
                "expression": (
                    f'(http.host eq "{host}" and '
                    f'http.request.uri.path eq "{route["path"]}")'
                ),
                "action": "route",
                "action_parameters": {"origin": {"port": route["port"]}},
            }
        )
    return rules


def managed_origin_rule_for_domain(rule: Dict[str, Any], domain: str) -> bool:
    if not str(rule.get("description", "")).startswith(MANAGED_RULE_PREFIX):
        return False
    host = domain.strip().lower()
    expr = str(rule.get("expression", "")).lower()
    return f'http.host eq "{host}"' in expr


def strip_managed_origin_rules(
    rules: List[Dict[str, Any]], domain: Optional[str] = None
) -> List[Dict[str, Any]]:
    host = domain.strip().lower() if domain else None
    filtered: List[Dict[str, Any]] = []
    for rule in rules:
        description = str(rule.get("description", ""))
        if not description.startswith(MANAGED_RULE_PREFIX):
            filtered.append(rule)
            continue
        if host and managed_origin_rule_for_domain(rule, host):
            continue
        if host is None:
            continue
        filtered.append(rule)
    return filtered


def get_origin_rules(zone_id: str, headers: Dict[str, str]) -> List[Dict[str, Any]]:
    result = call_json_api(
        "GET",
        f"{CF_API_BASE}/zones/{zone_id}/rulesets/phases/{ORIGIN_RULE_PHASE}/entrypoint",
        headers=headers,
        exit_on_http_error=False,
    )
    if not result.get("success", False):
        return []
    ruleset = result.get("result") or {}
    rules = ruleset.get("rules")
    if isinstance(rules, list):
        return rules
    return []


def origin_rule_host(rule: Dict[str, Any]) -> str:
    expr = str(rule.get("expression", ""))
    match = re.search(r'http\.host eq "([^"]+)"', expr, re.I)
    return match.group(1) if match else "?"


def origin_rule_port(rule: Dict[str, Any]) -> str:
    origin = ((rule.get("action_parameters") or {}).get("origin") or {})
    port = origin.get("port")
    return str(port) if port is not None else "?"


def is_origin_rule_limit_error(result: Dict[str, Any]) -> bool:
    for item in result.get("errors") or []:
        message = str(item.get("message", "")).lower()
        if any(
            token in message
            for token in ("limit", "quota", "maximum", "exceeded", "too many", "rule")
        ):
            return True
        try:
            if int(item.get("code", 0)) in (10006, 20127, 20217):
                return True
        except (TypeError, ValueError):
            pass
    return False


def format_origin_rule_line(index: int, rule: Dict[str, Any]) -> str:
    description = str(rule.get("description") or "(no description)")
    host = origin_rule_host(rule)
    port = origin_rule_port(rule)
    kind = "managed" if description.startswith(MANAGED_RULE_PREFIX) else "external"
    path_match = re.search(r'http\.request\.uri\.path eq "([^"]+)"', str(rule.get("expression", "")))
    path = path_match.group(1) if path_match else ""
    extra = f" path={path}" if path else ""
    return f"{index}. [{kind}] {host}{extra} -> :{port} | {description}"


def prompt_delete_origin_rules(rules: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    if not rules:
        exit_error("Origin Rules are empty; cannot continue")

    print("\nCloudflare Origin Rules quota reached. Delete selected rules and retry:")
    for i, rule in enumerate(rules, 1):
        print(format_origin_rule_line(i, rule))

    raw = input("\nEnter rule numbers to delete(comma-separated, Enter=cancel): ").strip()
    if not raw:
        return None

    remove_indexes: Set[int] = set()
    for token in raw.replace(" ", "").split(","):
        if not token:
            continue
        if not token.isdigit():
            exit_error(f"Invalid index: {token}")
        idx = int(token)
        if idx < 1 or idx > len(rules):
            exit_error(f"Index out of range: {idx}")
        remove_indexes.add(idx)

    if not remove_indexes:
        return None

    kept = [rule for i, rule in enumerate(rules, 1) if i not in remove_indexes]
    print(f"Will delete {len(remove_indexes)} rules and keep {len(kept)} rules")
    return kept


def put_origin_rules(zone_id: str, headers: Dict[str, str], rules: List[Dict[str, Any]]) -> None:
    payload = {"rules": rules}
    result = call_cf_api_result(
        "PUT",
        f"/zones/{zone_id}/rulesets/phases/{ORIGIN_RULE_PHASE}/entrypoint",
        headers=headers,
        data=payload,
    )
    if result.get("success", False):
        return
    if is_origin_rule_limit_error(result):
        errors = result.get("errors") or [{"message": "Origin Rules quota reached"}]
        print(json.dumps(errors, ensure_ascii=False))
        next_rules = prompt_delete_origin_rules(rules)
        if next_rules is None:
            exit_error("Origin Rules deletion cancelled")
        put_origin_rules(zone_id, headers, next_rules)
        return
    errors = result.get("errors") or [{"message": "Unknown Cloudflare API error"}]
    print(json.dumps(errors, ensure_ascii=False))
    sys.exit(1)


def apply_origin_rules(
    zone_id: str, headers: Dict[str, str], domain: str, routes: List[Dict[str, Any]]
) -> None:
    existing = get_origin_rules(zone_id, headers)
    next_rules = strip_managed_origin_rules(existing, domain) + build_origin_rules(domain, routes)
    put_origin_rules(zone_id, headers, next_rules)


def get_config_rules(zone_id: str, headers: Dict[str, str]) -> List[Dict[str, Any]]:
    result = call_json_api(
        "GET",
        f"{CF_API_BASE}/zones/{zone_id}/rulesets/phases/{CONFIG_RULE_PHASE}/entrypoint",
        headers=headers,
        exit_on_http_error=False,
    )
    if not result.get("success", False):
        return []
    ruleset = result.get("result") or {}
    rules = ruleset.get("rules")
    if isinstance(rules, list):
        return rules
    return []


def put_config_rules(zone_id: str, headers: Dict[str, str], rules: List[Dict[str, Any]]) -> None:
    result = call_cf_api_result(
        "PUT",
        f"/zones/{zone_id}/rulesets/phases/{CONFIG_RULE_PHASE}/entrypoint",
        headers=headers,
        data={"rules": rules},
    )
    if result.get("success", False):
        return
    errors = result.get("errors") or [{"message": "Failed to write Cloudflare Configuration Rules"}]
    print(json.dumps(errors, ensure_ascii=False))
    sys.exit(1)


def managed_ssl_config_rule_for_domain(rule: Dict[str, Any], domain: str) -> bool:
    description = str(rule.get("description", ""))
    if not description.startswith(MANAGED_SSL_RULE_PREFIX):
        return False
    host = normalize_domain(domain)
    expr = str(rule.get("expression", "")).lower()
    return f'http.host eq "{host}"' in expr


def strip_managed_ssl_config_rules(
    rules: List[Dict[str, Any]], domains: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    normalized = {normalize_domain(domain) for domain in domains} if domains else set()
    filtered: List[Dict[str, Any]] = []
    for rule in rules:
        description = str(rule.get("description", ""))
        if not description.startswith(MANAGED_SSL_RULE_PREFIX):
            filtered.append(rule)
            continue
        if not normalized:
            continue
        expr = str(rule.get("expression", "")).lower()
        if any(f'http.host eq "{host}"' in expr for host in normalized):
            continue
        filtered.append(rule)
    return filtered


def build_ssl_config_rule(domain: str, mode: str, role: str) -> Dict[str, Any]:
    host = normalize_domain(domain)
    ref = f"cf_deployer_ssl_{role}_{uuid.uuid5(uuid.NAMESPACE_DNS, role + ':' + host).hex[:12]}"
    return {
        "ref": ref,
        "description": f"{MANAGED_SSL_RULE_PREFIX}{role} {host}",
        "enabled": True,
        "expression": f'(http.host eq "{host}")',
        "action": "set_config",
        "action_parameters": {"ssl": mode},
    }


def apply_ssl_config_rules(
    zone_id: str,
    headers: Dict[str, str],
    rules_by_domain: List[Tuple[str, str, str]],
) -> None:
    domains = [domain for domain, _, _ in rules_by_domain]
    existing = get_config_rules(zone_id, headers)
    next_rules = strip_managed_ssl_config_rules(existing, domains)
    for domain, mode, role in rules_by_domain:
        next_rules.append(build_ssl_config_rule(domain, mode, role))
    put_config_rules(zone_id, headers, next_rules)


def remove_ssl_config_rules_for_domain(zone_id: str, headers: Dict[str, str], domain: str) -> None:
    existing = get_config_rules(zone_id, headers)
    put_config_rules(zone_id, headers, strip_managed_ssl_config_rules(existing, [domain]))


def client_email_for_route(short_id: str, protocol: str) -> str:
    """3x-ui client email: lowercase letters and digits, no @, matching panel validation."""
    return f"{short_id.lower()}{PROTOCOL_SUFFIX[protocol]}"


def now_ms() -> int:
    return int(time.time() * 1000)


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    )
    return cursor.fetchone() is not None


def has_v3_client_schema(conn: sqlite3.Connection) -> bool:
    return table_exists(conn, "clients") and table_exists(conn, "client_inbounds")


def inbound_client_entry(protocol: str, user_uuid: str, email: str, *, v3: bool = True) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "email": email,
        "limitIp": 0,
        "totalGB": 0,
        "expiryTime": 0,
        "enable": True,
        "subId": "",
        "comment": "",
        "reset": 0,
        "flow": "",
        "tgId": 0 if v3 else "",
    }
    if protocol == "vless":
        entry["id"] = user_uuid
    elif protocol == "trojan":
        entry["password"] = user_uuid
    elif protocol == "vmess":
        entry["id"] = user_uuid
        entry["alterId"] = 0
        entry["security"] = "auto"
    else:
        raise ValueError(f"Unsupported protocol: {protocol}")
    return entry


def ensure_vless_crypto_fields(payload: Dict[str, Any]) -> None:
    payload["decryption"] = "none"
    payload["encryption"] = "none"


def protocol_settings(protocol: str, user_uuid: str, email: str, *, v3: bool = True) -> Dict[str, Any]:
    client = inbound_client_entry(protocol, user_uuid, email, v3=v3)
    if protocol == "vless":
        return {
            "clients": [client],
            "decryption": "none",
            "encryption": "none",
            "fallbacks": [],
        }
    if protocol == "trojan":
        return {
            "clients": [client],
            "fallbacks": [],
        }
    if protocol == "vmess":
        return {
            "clients": [client],
        }
    raise ValueError(f"Unsupported protocol: {protocol}")


def parse_inbound_client_from_settings(protocol: str, settings_text: str) -> Optional[Dict[str, Any]]:
    try:
        payload = json.loads(settings_text or "{}")
    except json.JSONDecodeError:
        return None
    clients = payload.get("clients")
    if not isinstance(clients, list) or not clients:
        return None
    first = clients[0]
    return first if isinstance(first, dict) else None


def client_email_from_tag(tag: str) -> Optional[str]:
    match = MANAGED_TAG_RE.match(tag or "")
    if not match:
        return None
    short_id, protocol = match.group(1), match.group(2).lower()
    return client_email_for_route(short_id, protocol)


def upsert_v3_client_record(
    cursor: sqlite3.Cursor,
    protocol: str,
    user_uuid: str,
    email: str,
    ts_ms: int,
) -> int:
    uuid_val = user_uuid if protocol in ("vless", "vmess") else ""
    password_val = user_uuid if protocol == "trojan" else ""
    security_val = "auto" if protocol == "vmess" else ""

    cursor.execute("SELECT id FROM clients WHERE email = ?", (email,))
    row = cursor.fetchone()
    if row:
        client_id = int(row[0])
        cursor.execute(
            """
            UPDATE clients
            SET uuid=?, password=?, flow='', security=?, limit_ip=0, total_gb=0,
                expiry_time=0, enable=1, tg_id=0, comment='', reset=0, updated_at=?
            WHERE id=?
            """,
            (uuid_val, password_val, security_val, ts_ms, client_id),
        )
        return client_id

    cursor.execute(
        """
        INSERT INTO clients (
            email, sub_id, uuid, password, auth, flow, security, reverse,
            limit_ip, total_gb, expiry_time, enable, tg_id, group_name, comment, reset,
            created_at, updated_at
        ) VALUES (?, '', ?, ?, '', '', ?, '', 0, 0, 0, 1, 0, '', '', 0, ?, ?)
        """,
        (email, uuid_val, password_val, security_val, ts_ms, ts_ms),
    )
    return int(cursor.lastrowid)


def link_v3_client_inbound(
    cursor: sqlite3.Cursor,
    client_id: int,
    inbound_id: int,
    ts_ms: int,
    flow: str = "",
) -> None:
    cursor.execute("DELETE FROM client_inbounds WHERE inbound_id = ?", (inbound_id,))
    cursor.execute(
        """
        INSERT INTO client_inbounds (client_id, inbound_id, flow_override, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (client_id, inbound_id, flow, ts_ms),
    )


def ensure_v3_client_traffic(cursor: sqlite3.Cursor, conn: sqlite3.Connection, inbound_id: int, email: str) -> None:
    if not table_exists(conn, "client_traffics"):
        return
    cursor.execute("SELECT 1 FROM client_traffics WHERE email = ? LIMIT 1", (email,))
    if cursor.fetchone():
        cursor.execute(
            """
            UPDATE client_traffics
            SET inbound_id=?, enable=1, total=0, expiry_time=0, reset=0
            WHERE email=?
            """,
            (inbound_id, email),
        )
        return
    cursor.execute(
        """
        INSERT INTO client_traffics (
            inbound_id, enable, email, up, down, expiry_time, total, reset, last_online
        ) VALUES (?, 1, ?, 0, 0, 0, 0, 0, 0)
        """,
        (inbound_id, email),
    )


def sync_v3_client_for_inbound(
    conn: sqlite3.Connection,
    inbound_id: int,
    protocol: str,
    user_uuid: str,
    email: str,
    ts_ms: Optional[int] = None,
) -> None:
    if not has_v3_client_schema(conn):
        return
    ts = ts_ms if ts_ms is not None else now_ms()
    cursor = conn.cursor()
    client_id = upsert_v3_client_record(cursor, protocol, user_uuid, email, ts)
    link_v3_client_inbound(cursor, client_id, inbound_id, ts)
    ensure_v3_client_traffic(cursor, conn, inbound_id, email)


def extract_client_uuid(protocol: str, client: Dict[str, Any]) -> str:
    if protocol == "trojan":
        return str(client.get("password") or "")
    return str(client.get("id") or "")


def repair_v3_missing_client_bindings(
    db_path: str,
    inbound_ids: Optional[List[int]] = None,
) -> int:
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error:
        return 0

    try:
        if not has_v3_client_schema(conn):
            return 0

        cursor = conn.cursor()
        if inbound_ids:
            placeholders = ",".join(["?"] * len(inbound_ids))
            cursor.execute(
                f"""
                SELECT id, tag, protocol, settings
                FROM inbounds
                WHERE id IN ({placeholders})
                  AND protocol IN ('vless', 'trojan', 'vmess')
                """,
                inbound_ids,
            )
        else:
            cursor.execute(
                """
                SELECT id, tag, protocol, settings
                FROM inbounds
                WHERE protocol IN ('vless', 'trojan', 'vmess')
                """
            )

        repaired = 0
        ts_ms = now_ms()
        for inbound_id, tag, protocol, settings_text in cursor.fetchall():
            inbound_id = int(inbound_id)
            protocol = str(protocol)
            cursor.execute(
                "SELECT COUNT(*) FROM client_inbounds WHERE inbound_id = ?",
                (inbound_id,),
            )
            if int(cursor.fetchone()[0]) > 0:
                continue

            client = parse_inbound_client_from_settings(protocol, str(settings_text or ""))
            if client is None:
                continue

            email = str(client.get("email") or "").strip()
            if not email:
                email = client_email_from_tag(str(tag or "")) or ""
            if not email:
                continue

            user_uuid = extract_client_uuid(protocol, client)
            if not user_uuid:
                continue

            if not str(client.get("email") or "").strip():
                payload = json.loads(settings_text or "{}")
                clients = payload.get("clients")
                if isinstance(clients, list) and clients and isinstance(clients[0], dict):
                    clients[0]["email"] = email
                    clients[0]["enable"] = True
                    if protocol == "vmess":
                        clients[0]["security"] = "auto"
                    clients[0]["tgId"] = 0
                    payload["clients"] = clients
                    if protocol == "vless":
                        ensure_vless_crypto_fields(payload)
                    cursor.execute(
                        "UPDATE inbounds SET settings=? WHERE id=?",
                        (json.dumps(payload, separators=(",", ":")), inbound_id),
                    )
            else:
                payload = json.loads(settings_text or "{}")
                changed = False
                if protocol == "vless":
                    old_d, old_e = payload.get("decryption"), payload.get("encryption")
                    ensure_vless_crypto_fields(payload)
                    if old_d != "none" or old_e != "none":
                        changed = True
                clients = payload.get("clients")
                if isinstance(clients, list) and clients and isinstance(clients[0], dict):
                    c0 = clients[0]
                    if c0.get("enable") is False:
                        c0["enable"] = True
                        changed = True
                    if protocol == "vmess" and not str(c0.get("security") or "").strip():
                        c0["security"] = "auto"
                        changed = True
                    if changed:
                        payload["clients"] = clients
                if changed:
                    cursor.execute(
                        "UPDATE inbounds SET settings=? WHERE id=?",
                        (json.dumps(payload, separators=(",", ":")), inbound_id),
                    )

            sync_v3_client_for_inbound(conn, inbound_id, protocol, user_uuid, email, ts_ms)
            repaired += 1

        if repaired:
            conn.commit()
        return repaired
    except sqlite3.Error as e:
        print(str(e))
        sys.exit(1)
    finally:
        conn.close()


def cleanup_v3_clients_for_inbounds(conn: sqlite3.Connection, inbound_ids: List[int]) -> None:
    if not inbound_ids or not has_v3_client_schema(conn):
        return

    cursor = conn.cursor()
    placeholders = ",".join(["?"] * len(inbound_ids))
    cursor.execute(
        f"""
        SELECT DISTINCT c.email
        FROM clients c
        JOIN client_inbounds ci ON ci.client_id = c.id
        WHERE ci.inbound_id IN ({placeholders})
        """,
        inbound_ids,
    )
    emails = [str(row[0]) for row in cursor.fetchall() if row and row[0]]

    cursor.execute(f"DELETE FROM client_inbounds WHERE inbound_id IN ({placeholders})", inbound_ids)

    for email in emails:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM client_inbounds ci
            JOIN clients c ON c.id = ci.client_id
            WHERE c.email = ?
            """,
            (email,),
        )
        if int(cursor.fetchone()[0]) > 0:
            continue
        cursor.execute("DELETE FROM clients WHERE email = ?", (email,))
        if table_exists(conn, "client_traffics"):
            cursor.execute("DELETE FROM client_traffics WHERE email = ?", (email,))


def protocol_settings_legacy(protocol: str, user_uuid: str) -> Dict[str, Any]:
    """Legacy 3x-ui: clients are embedded in settings, and email may be empty."""
    if protocol == "vless":
        return {
            "clients": [{"id": user_uuid, "flow": "", "email": ""}],
            "decryption": "none",
            "encryption": "none",
            "fallbacks": [],
        }
    if protocol == "trojan":
        return {
            "clients": [{"password": user_uuid, "flow": "", "email": ""}],
            "fallbacks": [],
        }
    if protocol == "vmess":
        return {
            "clients": [{"id": user_uuid, "alterId": 0, "email": ""}],
        }
    raise ValueError(f"Unsupported protocol: {protocol}")


def normalize_existing_inbound_client_email(db_path: str) -> None:
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error as e:
        exit_error(str(e))

    try:
        v3_schema = has_v3_client_schema(conn)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, tag, settings FROM inbounds WHERE protocol IN ('vless','trojan','vmess')"
        )
        rows = cursor.fetchall()
        changed: List[tuple[str, int]] = []
        for row in rows:
            inbound_id = int(row[0])
            tag = str(row[1] or "")
            settings_text = str(row[2] or "")
            try:
                payload = json.loads(settings_text or "{}")
            except json.JSONDecodeError:
                continue
            clients = payload.get("clients")
            if not isinstance(clients, list):
                continue

            updated = False
            for client in clients:
                if not isinstance(client, dict):
                    continue
                email = str(client.get("email") or "").strip()
                if not email and v3_schema:
                    derived = client_email_from_tag(tag)
                    if derived:
                        client["email"] = derived
                        updated = True
                        continue
                if not email and v3_schema:
                    continue
                if client.get("email") is None:
                    client["email"] = ""
                    updated = True
                elif "email" not in client:
                    client["email"] = ""
                    updated = True

            if updated:
                changed.append((json.dumps(payload, separators=(",", ":")), inbound_id))

        if changed:
            cursor.executemany("UPDATE inbounds SET settings=? WHERE id=?", changed)
            conn.commit()
    except sqlite3.Error as e:
        print(str(e))
        sys.exit(1)
    finally:
        conn.close()


def maybe_repair_v3_client_bindings(
    db_path: str,
    mode: str,
    state: Optional[Dict[str, Any]] = None,
) -> None:
    if mode == "uninstall" or not os.path.exists(db_path):
        return
    inbound_ids: Optional[List[int]] = None
    if state and isinstance(state.get("inbound_ids"), list):
        parsed: List[int] = []
        for item in state["inbound_ids"]:
            try:
                parsed.append(int(item))
            except Exception:
                continue
        if parsed:
            inbound_ids = parsed
    repaired = repair_v3_missing_client_bindings(db_path, inbound_ids)
    if repaired:
        print(f"Repaired {repaired} 3x-ui v3 inbound client bindings")
        restart_xui_service()


def ws_stream_settings(path: str) -> Dict[str, Any]:
    return {
        "network": "ws",
        "security": "none",
        "wsSettings": {"path": path},
    }


def sniffing_settings() -> Dict[str, Any]:
    return {
        "enabled": True,
        "destOverride": ["http", "tls"],
        "metadataOnly": False,
        "routeOnly": False,
    }


def allocate_settings() -> Dict[str, Any]:
    return {"strategy": "always", "refresh": 5, "concurrency": 3}


def build_inbound_payload(protocol: str, user_uuid: str, short_id: str, route: Dict[str, Any]) -> Dict[str, Any]:
    email = client_email_for_route(short_id, protocol)
    return {
        "enable": True,
        "remark": f"{short_id}-{protocol}",
        "listen": "",
        "port": route["port"],
        "protocol": protocol,
        "expiryTime": 0,
        "tag": f"{short_id}-{protocol}",
        "settings": json.dumps(protocol_settings(protocol, user_uuid, email, v3=True), separators=(",", ":")),
        "streamSettings": json.dumps(ws_stream_settings(route["path"]), separators=(",", ":")),
        "sniffing": json.dumps(sniffing_settings(), separators=(",", ":")),
    }


def load_existing_ports_db(conn: sqlite3.Connection) -> Set[int]:
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT port FROM inbounds")
    except sqlite3.Error:
        return set()
    ports = set()
    for row in cursor.fetchall():
        try:
            ports.add(int(row[0]))
        except Exception:
            continue
    return ports


def load_existing_ports_api(client: XuiPanelClient) -> Set[int]:
    ports: Set[int] = set()
    for inbound in client.list_inbounds():
        try:
            ports.add(int(inbound.get("port", 0)))
        except (TypeError, ValueError):
            continue
    return ports


def random_ports(count: int, existing: Set[int]) -> List[int]:
    selected = set()
    while len(selected) < count:
        p = random.randint(PORT_MIN, PORT_MAX)
        if p in existing or p in selected:
            continue
        selected.add(p)
    return list(selected)


def parse_protocol_selection(raw: str) -> List[str]:
    text = raw.strip().lower()
    if not text:
        return list(PROTOCOL_ORDER)

    index_mapping = {"1": "vless", "2": "trojan", "3": "vmess"}
    name_mapping = {"vless": "vless", "trojan": "trojan", "vmess": "vmess"}

    selected: List[str] = []
    for token in text.replace(" ", "").split(","):
        if not token:
            continue
        protocol = index_mapping.get(token) or name_mapping.get(token)
        if protocol is None:
            exit_error(f"Invalid protocol selection: {token}")
        if protocol not in selected:
            selected.append(protocol)

    if not selected:
        exit_error("Select at least one protocol")
    return selected


def get_inbounds_schema(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(inbounds)")
    rows = cursor.fetchall()
    schema: List[Dict[str, Any]] = []
    for row in rows:
        schema.append(
            {
                "name": row[1],
                "type": (row[2] or "").upper(),
                "notnull": bool(row[3]),
                "default": row[4],
                "pk": bool(row[5]),
            }
        )
    return schema


def load_template_inbound(conn: sqlite3.Connection) -> Dict[str, Any]:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM inbounds ORDER BY id LIMIT 1")
    row = cursor.fetchone()
    if row is None:
        return {}
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


def infer_default_value(col_type: str):
    if "INT" in col_type:
        return 0
    if "REAL" in col_type or "FLOA" in col_type or "DOUB" in col_type:
        return 0
    if "BLOB" in col_type:
        return b""
    return ""


def insert_inbounds_db(
    db_path: str,
    user_uuid: str,
    short_id: str,
    routes: List[Dict[str, Any]],
) -> List[int]:
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error as e:
        exit_error(str(e))

    try:
        schema = get_inbounds_schema(conn)
        if not schema:
            exit_error("inbounds table not found")
        template = load_template_inbound(conn)
        cursor = conn.cursor()
        inserted_ids: List[int] = []
        v3_schema = has_v3_client_schema(conn)
        ts_ms = now_ms()

        for route in routes:
            protocol = route["protocol"]
            email = client_email_for_route(short_id, protocol)
            settings = (
                protocol_settings(protocol, user_uuid, email, v3=True)
                if v3_schema
                else protocol_settings_legacy(protocol, user_uuid)
            )
            row_data = dict(template)
            row_data.update(
                {
                    "user_id": 1,
                    "enable": 1,
                    "up": 0,
                    "down": 0,
                    "total": 0,
                    "remark": f"{short_id}-{protocol}",
                    "listen": "",
                    "port": route["port"],
                    "protocol": protocol,
                    "settings": json.dumps(settings, separators=(",", ":")),
                    "stream_settings": json.dumps(ws_stream_settings(route["path"]), separators=(",", ":")),
                    "sniffing": json.dumps(sniffing_settings(), separators=(",", ":")),
                    "allocate": json.dumps(allocate_settings(), separators=(",", ":")),
                    "tag": f"{short_id}-{protocol}",
                }
            )

            columns: List[str] = []
            values: List[Any] = []
            for col in schema:
                name = col["name"]
                if col["pk"]:
                    continue
                if name in row_data:
                    columns.append(name)
                    values.append(row_data[name])
                    continue
                if col["notnull"] and col["default"] is None:
                    columns.append(name)
                    values.append(infer_default_value(col["type"]))

            placeholders = ",".join(["?"] * len(columns))
            sql = f"INSERT INTO inbounds ({','.join(columns)}) VALUES ({placeholders})"
            cursor.execute(sql, values)
            inbound_id = int(cursor.lastrowid)
            inserted_ids.append(inbound_id)
            if v3_schema:
                sync_v3_client_for_inbound(conn, inbound_id, protocol, user_uuid, email, ts_ms)

        conn.commit()
        return inserted_ids
    except sqlite3.Error as e:
        print(str(e))
        sys.exit(1)
    finally:
        conn.close()


def delete_inbounds_db(db_path: str, inbound_ids: List[int], tags: List[str]) -> None:
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error as e:
        exit_error(str(e))

    try:
        cursor = conn.cursor()
        if inbound_ids:
            cleanup_v3_clients_for_inbounds(conn, inbound_ids)
            placeholders = ",".join(["?"] * len(inbound_ids))
            cursor.execute(f"DELETE FROM inbounds WHERE id IN ({placeholders})", inbound_ids)
        elif tags:
            cursor.execute(
                f"SELECT id FROM inbounds WHERE tag IN ({','.join(['?'] * len(tags))})",
                tags,
            )
            resolved_ids = [int(row[0]) for row in cursor.fetchall()]
            if resolved_ids:
                cleanup_v3_clients_for_inbounds(conn, resolved_ids)
            placeholders = ",".join(["?"] * len(tags))
            cursor.execute(f"DELETE FROM inbounds WHERE tag IN ({placeholders})", tags)
        conn.commit()
    except sqlite3.Error as e:
        print(str(e))
        sys.exit(1)
    finally:
        conn.close()


def restart_xui_service() -> None:
    try:
        result = subprocess.run(
            ["systemctl", "restart", "x-ui"],
            capture_output=True,
            text=True,
            check=True,
        )
        if result.stderr.strip():
            print(result.stderr.strip())
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        stdout = (e.stdout or "").strip()
        if stderr:
            print(stderr)
        elif stdout:
            print(stdout)
        else:
            print(str(e))
        sys.exit(1)


def create_inbounds_via_api(
    client: XuiPanelClient,
    user_uuid: str,
    short_id: str,
    routes: List[Dict[str, Any]],
) -> List[int]:
    inserted_ids: List[int] = []
    for route in routes:
        protocol = route["protocol"]
        payload = build_inbound_payload(protocol, user_uuid, short_id, route)
        created = client.add_inbound(payload)
        inbound_id = created.get("id")
        if inbound_id is None:
            exit_error(f"Failed to create {protocol} inbound: API did not return id")
        inserted_ids.append(int(inbound_id))
    client.restart_xray()
    return inserted_ids


def delete_inbounds_via_api(client: XuiPanelClient, inbound_ids: List[int]) -> None:
    for inbound_id in inbound_ids:
        client.delete_inbound(inbound_id)
    if inbound_ids:
        client.restart_xray()


def create_inbounds(
    backend: str,
    user_uuid: str,
    short_id: str,
    routes: List[Dict[str, Any]],
    panel: Optional[XuiPanelClient] = None,
) -> List[int]:
    if backend == BACKEND_API:
        if panel is None:
            exit_error("API mode requires a logged-in panel client")
        return create_inbounds_via_api(panel, user_uuid, short_id, routes)
    inbound_ids = insert_inbounds_db(DB_PATH, user_uuid, short_id, routes)
    restart_xui_service()
    return inbound_ids


def delete_managed_inbounds(
    backend: str,
    inbound_ids: List[int],
    tags: List[str],
    panel: Optional[XuiPanelClient] = None,
) -> None:
    if backend == BACKEND_API:
        if panel is None:
            exit_error("API mode requires a logged-in panel client")
        delete_inbounds_via_api(panel, inbound_ids)
        return
    delete_inbounds_db(DB_PATH, inbound_ids, tags)
    restart_xui_service()


def build_links(
    user_uuid: str,
    domain: str,
    routes: List[Dict[str, Any]],
    deployer_cf_url: Optional[str] = None,
) -> Dict[str, str]:
    base_root = normalize_deployer_cf_url(deployer_cf_url or current_deployer_cf_url())
    base_url = f"{base_root}/{user_uuid}/sub"
    common = {
        "domain": domain,
        "epd": "yes",
        "epi": "yes",
        "egi": "no",
        "dkby": "yes",
    }

    links = {}
    for route in routes:
        protocol = route["protocol"]
        params = dict(common)
        params["ev"] = "no"
        params["et"] = "no"
        params["evm"] = "no"
        params[PROTOCOL_QUERY_FLAG[protocol]] = "yes"
        params["path"] = route["path"]
        links[protocol] = f"{base_url}?{parse.urlencode(params, safe='', quote_via=parse.quote)}"

    return links


def load_last_state() -> Optional[Dict[str, Any]]:
    if not os.path.exists(STATE_PATH):
        return None
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        exit_error(f"Failed to read last state: {e}")
    if not isinstance(data, dict):
        return None
    return data


def save_last_state(state: Dict[str, Any]) -> None:
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
        os.chmod(STATE_PATH, 0o600)
    except OSError as e:
        exit_error(f"Failed to save last state: {e}")


def remove_last_state() -> None:
    try:
        if os.path.exists(STATE_PATH):
            os.remove(STATE_PATH)
    except OSError as e:
        exit_error(f"Failed to delete last state: {e}")


def save_last_links_snapshot(domain: str, user_uuid: str, links: Dict[str, str], order: List[str]) -> None:
    lines = [
        "Last generated subscriptions",
        f"Domain: {domain}",
        f"UUID: {user_uuid}",
        "",
    ]
    for protocol in order:
        link = links.get(protocol)
        if link:
            lines.append(f"{PROTOCOL_LABEL[protocol]} subscription {link}")
    lines.append("")
    content = "\n".join(lines)
    try:
        with open(LAST_LINKS_PATH, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(LAST_LINKS_PATH, 0o600)
    except OSError as e:
        exit_error(f"Failed to save last subscriptions: {e}")


def extract_client_key(protocol: str) -> str:
    if protocol == "trojan":
        return "password"
    return "id"


def extract_uuid_from_settings(protocol: str, settings_text: str) -> str:
    try:
        payload = json.loads(settings_text or "{}")
    except json.JSONDecodeError:
        return ""
    clients = payload.get("clients")
    if not isinstance(clients, list) or not clients:
        return ""
    first = clients[0] if isinstance(clients[0], dict) else {}
    key = extract_client_key(protocol)
    value = str(first.get(key, "")).strip()
    return value


def extract_ws_path(stream_settings_text: str) -> str:
    if isinstance(stream_settings_text, dict):
        payload = stream_settings_text
    else:
        try:
            payload = json.loads(stream_settings_text or "{}")
        except json.JSONDecodeError:
            return ""
    ws = payload.get("wsSettings")
    if not isinstance(ws, dict):
        return ""
    path = str(ws.get("path", "")).strip()
    if not path.startswith("/"):
        return ""
    return path


def extract_short_id(path: str, tag: str, remark: str) -> str:
    path_match = re.match(r"^/([0-9a-f]{8})-(vl|tr|vm)$", path.strip().lower())
    if path_match:
        return path_match.group(1)

    for text in (tag, remark):
        m = re.match(r"^([0-9a-f]{8})-(vless|trojan|vmess)$", str(text).strip().lower())
        if m:
            return m.group(1)
    return ""


def _group_legacy_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {}

    grouped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        sid = row["short_id"]
        bucket = grouped.setdefault(
            sid,
            {"max_id": 0, "uuid_votes": {}, "routes": {}, "enabled_count": 0},
        )
        bucket["max_id"] = max(bucket["max_id"], row["id"])
        bucket["routes"][row["protocol"]] = {"protocol": row["protocol"], "path": row["path"], "port": 0}
        bucket["uuid_votes"][row["uuid"]] = bucket["uuid_votes"].get(row["uuid"], 0) + 1
        if row["enable"] == 1:
            bucket["enabled_count"] += 1

    best_sid = ""
    best_score = (-1, -1, -1)
    for sid, data in grouped.items():
        score = (data["enabled_count"], len(data["routes"]), data["max_id"])
        if score > best_score:
            best_score = score
            best_sid = sid

    if not best_sid:
        return {}

    best = grouped[best_sid]
    if not best["routes"]:
        return {}
    best_uuid = max(best["uuid_votes"].items(), key=lambda x: x[1])[0]
    order = [p for p in PROTOCOL_ORDER if p in best["routes"]]
    return {
        "short_id": best_sid,
        "uuid": best_uuid,
        "routes": [best["routes"][p] for p in order],
        "selected_protocols": order,
    }


def load_legacy_routes_from_db() -> Dict[str, Any]:
    try:
        conn = sqlite3.connect(DB_PATH)
    except sqlite3.Error as e:
        exit_error(str(e))

    rows: List[Dict[str, Any]] = []
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, protocol, settings, stream_settings, tag, remark, enable "
            "FROM inbounds WHERE protocol IN ('vless','trojan','vmess') ORDER BY id DESC"
        )
        for item in cursor.fetchall():
            protocol = str(item[1]).strip().lower()
            if protocol not in PROTOCOL_ORDER:
                continue
            ws_path = extract_ws_path(str(item[3] or ""))
            if not ws_path:
                continue
            short_id = extract_short_id(ws_path, str(item[4] or ""), str(item[5] or ""))
            if not short_id:
                continue
            user_uuid = extract_uuid_from_settings(protocol, str(item[2] or ""))
            if not user_uuid:
                continue
            rows.append(
                {
                    "id": int(item[0]),
                    "protocol": protocol,
                    "path": ws_path,
                    "short_id": short_id,
                    "uuid": user_uuid,
                    "enable": int(item[6] or 0),
                }
            )
    except sqlite3.Error as e:
        exit_error(str(e))
    finally:
        conn.close()

    return _group_legacy_rows(rows)


def load_legacy_routes_from_panel(client: XuiPanelClient) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for item in client.list_inbounds():
        protocol = str(item.get("protocol", "")).strip().lower()
        if protocol not in PROTOCOL_ORDER:
            continue
        stream_settings = item.get("streamSettings")
        if isinstance(stream_settings, dict):
            stream_text = json.dumps(stream_settings)
        else:
            stream_text = str(stream_settings or "")
        ws_path = extract_ws_path(stream_text)
        if not ws_path:
            continue
        short_id = extract_short_id(ws_path, str(item.get("tag") or ""), str(item.get("remark") or ""))
        if not short_id:
            continue
        settings = item.get("settings")
        if isinstance(settings, dict):
            settings_text = json.dumps(settings)
        else:
            settings_text = str(settings or "")
        user_uuid = extract_uuid_from_settings(protocol, settings_text)
        if not user_uuid:
            continue
        inbound_id = item.get("id")
        if inbound_id is None:
            continue
        rows.append(
            {
                "id": int(inbound_id),
                "protocol": protocol,
                "path": ws_path,
                "short_id": short_id,
                "uuid": user_uuid,
                "enable": 1 if item.get("enable") else 0,
            }
        )
    return _group_legacy_rows(rows)


def print_last_links() -> None:
    if os.path.exists(LAST_LINKS_PATH):
        try:
            with open(LAST_LINKS_PATH, "r", encoding="utf-8") as f:
                content = f.read().strip()
        except OSError as e:
            exit_error(f"Failed to read last subscriptions: {e}")
        if content:
            print(content)
            return

    state = load_last_state()
    if state:
        links = state.get("links")
        if isinstance(links, dict):
            order = state.get("selected_protocols") or PROTOCOL_ORDER
            for protocol in order:
                p = str(protocol).lower()
                if p in links:
                    print(f"{PROTOCOL_LABEL.get(p, p.upper())} subscription {links[p]}")
            return

        legacy_domain = str(state.get("domain", "")).strip()
        legacy_uuid = str(state.get("uuid", "")).strip()
        legacy_routes = state.get("routes")
        if legacy_domain and legacy_uuid and isinstance(legacy_routes, list) and legacy_routes:
            links = build_links(
                legacy_uuid,
                legacy_domain,
                legacy_routes,
                current_deployer_cf_url(state),
            )
            order = state.get("selected_protocols") or [r.get("protocol") for r in legacy_routes]
            order = [str(p).lower() for p in order if str(p).lower() in links]
            save_last_links_snapshot(legacy_domain, legacy_uuid, links, order)
            for protocol in order:
                print(f"{PROTOCOL_LABEL.get(protocol, protocol.upper())} subscription {links[protocol]}")
            return

    if os.path.exists(DB_PATH):
        recovered = load_legacy_routes_from_db()
        if recovered:
            domain = input("Cache not found. Enter bound domain for legacy reconstruction: ").strip()
            if not domain:
                exit_error("Domain cannot be empty")
            links = build_links(str(recovered["uuid"]), domain, recovered["routes"], current_deployer_cf_url())
            order = recovered["selected_protocols"]
            save_last_links_snapshot(domain, str(recovered["uuid"]), links, order)
            for protocol in order:
                if protocol in links:
                    print(f"{PROTOCOL_LABEL[protocol]} subscription {links[protocol]}")
            return

    if os.environ.get("XUI_API_TOKEN") or os.environ.get("XUI_PANEL_URL"):
        runtime = detect_xui_environment()
        panel = setup_panel_client(runtime, interactive=True)
        recovered = load_legacy_routes_from_panel(panel)
        if recovered:
            domain = input("Cache not found. Enter bound domain for legacy reconstruction: ").strip()
            if not domain:
                exit_error("Domain cannot be empty")
            links = build_links(str(recovered["uuid"]), domain, recovered["routes"], current_deployer_cf_url())
            order = recovered["selected_protocols"]
            save_last_links_snapshot(domain, str(recovered["uuid"]), links, order)
            for protocol in order:
                if protocol in links:
                    print(f"{PROTOCOL_LABEL[protocol]} subscription {links[protocol]}")
            return

    exit_error("No previous subscriptions available")


def restore_dns_record(
    zone_id: str,
    domain: str,
    headers: Dict[str, str],
    dns_backup: Optional[Dict[str, Any]],
    managed_dns_record_id: str,
) -> None:
    existed = bool((dns_backup or {}).get("existed"))
    record = (dns_backup or {}).get("record") or {}
    if existed:
        record_id = str(record.get("id", "")).strip()
        if not record_id:
            current = get_dns_record(zone_id, domain, headers)
            if current:
                record_id = str(current.get("id", "")).strip()
        if not record_id:
            return
        payload = {
            "type": record.get("type", "A"),
            "name": record.get("name", domain),
            "content": record.get("content", ""),
            "proxied": bool(record.get("proxied", False)),
            "ttl": int(record.get("ttl", 1)),
        }
        if not payload["content"]:
            return
        call_cf_api("PUT", f"/zones/{zone_id}/dns_records/{record_id}", headers=headers, data=payload)
        return

    record_id = managed_dns_record_id.strip()
    if not record_id:
        current = get_dns_record(zone_id, domain, headers)
        if current:
            record_id = str(current.get("id", "")).strip()
    if record_id:
        call_cf_api("DELETE", f"/zones/{zone_id}/dns_records/{record_id}", headers=headers)


def uninstall_last_config(
    state: Dict[str, Any],
    headers: Dict[str, str],
    backend: str,
    panel: Optional[XuiPanelClient] = None,
) -> None:
    domain = str(state.get("domain", "")).strip()
    zone_id = str(state.get("zone_id", "")).strip()
    if not domain or not zone_id:
        exit_error("Last state is missing domain or zone_id; cannot uninstall")

    current_rules = get_origin_rules(zone_id, headers)
    put_origin_rules(zone_id, headers, strip_managed_origin_rules(current_rules, domain))
    remove_ssl_config_rules_for_domain(zone_id, headers, domain)

    ssl_backup = str(state.get("ssl_backup", "")).strip()
    if ssl_backup:
        print("Legacy state detected. Restoring Cloudflare zone-wide SSL mode.")
        set_ssl_mode(zone_id, headers, ssl_backup)

    restore_dns_record(
        zone_id=zone_id,
        domain=domain,
        headers=headers,
        dns_backup=state.get("dns_backup"),
        managed_dns_record_id=str(state.get("managed_dns_record_id", "")),
    )

    inbound_ids: List[int] = []
    for item in state.get("inbound_ids", []):
        try:
            inbound_ids.append(int(item))
        except Exception:
            continue
    tags = [str(x) for x in state.get("tags", []) if str(x).strip()]
    delete_managed_inbounds(backend, inbound_ids, tags, panel=panel)
    sync_cloudflare_origin_firewall_ports([])


def run_deploy_install(
    context: Optional[Dict[str, Any]] = None,
    *,
    panel_configured: bool = False,
) -> None:
    last_state = load_last_state()
    if last_state is not None:
        last_domain = str(last_state.get("domain", "unknown domain"))
        exit_error(f"Detected last deployment({last_domain}); run uninstall first")

    context = context or prompt_deploy_context()
    if not panel_configured:
        configure_existing_panel_cloudflare(context)

    backend, runtime, reason = resolve_backend()
    print(f"x-ui write backend: {backend_label(backend)} ({reason})")
    panel = None
    if backend == BACKEND_DB:
        if not os.path.exists(DB_PATH):
            exit_error(f"3x-ui database not found: {DB_PATH}")
        normalize_existing_inbound_client_email(DB_PATH)
        maybe_repair_v3_client_bindings(DB_PATH, "install", last_state)
    else:
        panel = setup_panel_client(runtime, interactive=False)

    deployer_cf_url = str(context["deployer_cf_url"])
    domain = str(context["domain"])
    selected_protocols = list(context["selected_protocols"])
    headers = context["headers"]
    zone_id = str(context["zone_id"])
    public_ip = str(context["public_ip"])

    user_uuid = str(uuid.uuid4())
    short_id = user_uuid[:8]

    if backend == BACKEND_API:
        existing_ports = load_existing_ports_api(panel)  # type: ignore[arg-type]
    else:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                existing_ports = load_existing_ports_db(conn)
        except sqlite3.Error as e:
            exit_error(str(e))

    ports = random_ports(len(selected_protocols), existing_ports)
    routes = []
    for i, protocol in enumerate(selected_protocols):
        routes.append(
            {
                "protocol": protocol,
                "port": ports[i],
                "path": f"/{short_id}-{PROTOCOL_SUFFIX[protocol]}",
            }
        )

    dns_before = get_dns_record(zone_id, domain, headers)
    origin_rules_before = get_origin_rules(zone_id, headers)

    inbound_ids = create_inbounds(
        backend,
        user_uuid=user_uuid,
        short_id=short_id,
        routes=routes,
        panel=panel,
    )

    managed_dns_record_id = upsert_dns_record(zone_id, domain, public_ip, headers)
    apply_ssl_config_rules(zone_id, headers, [(domain, "flexible", "node")])
    apply_origin_rules(zone_id, headers, domain, routes)
    open_cloudflare_origin_ports_if_active([int(route["port"]) for route in routes])

    links = build_links(user_uuid, domain, routes, deployer_cf_url)
    save_last_links_snapshot(domain=domain, user_uuid=user_uuid, links=links, order=selected_protocols)

    state_version = 2 if backend == BACKEND_API else 1
    save_last_state(
        {
            "version": state_version,
            "backend": backend,
            "domain": domain,
            "zone_id": zone_id,
            "uuid": user_uuid,
            "short_id": short_id,
            "deployer_cf_url": deployer_cf_url,
            "routes": routes,
            "inbound_ids": inbound_ids,
            "tags": [f"{short_id}-{p}" for p in selected_protocols],
            "managed_dns_record_id": managed_dns_record_id,
            "dns_backup": {
                "existed": dns_before is not None,
                "record": dns_before,
            },
            "node_ssl_config_mode": "flexible",
            "origin_rules_backup": origin_rules_before,
            "links": links,
            "selected_protocols": selected_protocols,
            "panel_domain": str(context.get("panel_domain") or ""),
        }
    )

    print("Success")
    print(f"Subscriptions saved to {LAST_LINKS_PATH}")
    for protocol in selected_protocols:
        print(f"{PROTOCOL_LABEL[protocol]} subscription {links[protocol]}")


def main() -> None:
    if len(sys.argv) > 1:
        if sys.argv[1] == "--sync-cloudflare-firewall":
            sync_cloudflare_firewall_from_state()
            return
        if sys.argv[1] in ("-h", "--help"):
            print("Usage: xui_cf_deployer.py [--sync-cloudflare-firewall]")
            return
        exit_error(f"Unknown argument: {sys.argv[1]}")

    ensure_cfd_command()
    resolve_deployer_cf_url()
    mode = select_mode_interactive()
    prompt_maybe_localize_xui_menu()
    last_state = load_last_state()

    if mode == "fresh":
        if is_xui_installed():
            exit_error("Detected an existing 3x-ui installation. Use mode 1 to deploy nodes.")
        if last_state is not None:
            last_domain = str(last_state.get("domain", "unknown domain"))
            exit_error(f"Detected last deployment({last_domain}); run uninstall first")
        context = prompt_deploy_context()
        ensure_xui_for_fresh_setup(context)
        run_deploy_install(context, panel_configured=True)
        return

    if mode == "panel":
        if not has_script_installed_panel():
            exit_error("This panel was not installed by this script; panel access info is unavailable")
        print_panel_access_info()
        return

    if mode == "xui_manage":
        print_xui_management_help()
        return

    if mode == "show":
        maybe_repair_v3_client_bindings(DB_PATH, mode, last_state)
        print_last_links()
        return

    if mode == "uninstall":
        if last_state is None:
            exit_error("No last deployment detected; cannot uninstall")
        backend, runtime, reason = resolve_backend(last_state)
        print(f"x-ui write backend: {backend_label(backend)} ({reason})")
        panel: Optional[XuiPanelClient] = None
        if backend == BACKEND_API:
            panel = setup_panel_client(runtime, interactive=False)
        cf_token = prompt_cf_api_token()
        headers = build_cf_headers(cf_token)
        uninstall_last_config(last_state, headers, backend, panel=panel)
        remove_last_state()
        print("Uninstall complete")
        return

    if not is_xui_installed():
        exit_error("3x-ui not detected. Use mode 4 (fresh install).")

    run_deploy_install()
    return


if __name__ == "__main__":
    main()
