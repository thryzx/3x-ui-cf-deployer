# 3x-ui Cloudflare Deployer

## Attribution

This repository is a modified fork of the original project:
[byJoey/xui-cf-deployer](https://github.com/byJoey/xui-cf-deployer).

Thanks to byJoey for the original open-source work. The base idea, script structure, and core deployment flow come from the upstream project. This repository contains personal modifications for a specific deployment workflow and is not an official upstream release. If this project is useful to you, please also review and respect the original project and author.

Main changes in this fork:

- Added configurable Deployer CF URL stored at `/etc/x-ui/cf_deployer_config.json`.
- Replaced Cloudflare Global API Key usage with scoped API Token support. The deployer itself does not persist the Cloudflare Token.
- Added 3x-ui panel domain binding with `panel.<root-domain>` as the default.
- Added proxied panel DNS and a Cloudflare SSL Configuration Rule with `strict` mode for the panel hostname.
- Stopped changing the Cloudflare zone-wide SSL mode. Node hostnames now get hostname-scoped `flexible` SSL rules.
- Added automatic selection of Cloudflare-supported HTTPS panel ports.
- Added panel certificate issuance through Cloudflare DNS-01 and automatic 3x-ui panel certificate configuration.
- Added best-effort firewall opening for active UFW/firewalld setups.
- Added Cloudflare-only firewall rules for generated node ports on active UFW/firewalld setups.
- Expanded documentation for token permissions, acme.sh token storage, and the security boundary of node `flexible` mode.

`xui_cf_deployer.py` is a Python 3 standard-library-only script for VPS deployment automation:

- Optionally install a fresh 3x-ui panel on a new server.
- Create VLESS, Trojan, and VMess nodes on demand.
- Create/delete inbounds through the 3x-ui REST API or direct SQLite writes.
- Configure Cloudflare DNS, Origin Rules, and hostname-scoped SSL Configuration Rules.
- Generate subscription links through a configurable Deployer CF service.
- Detect the last deployment and support one-step rollback.

## Requirements

- Mode 1, deploy nodes: an existing and working 3x-ui panel is required.
- Mode 4, fresh install: only for new servers without an existing 3x-ui installation.
- Legacy default write path: `/etc/x-ui/x-ui.db` exists, then the script writes SQLite directly and restarts `x-ui`.
- Optional modern write path: panel API is reachable with credentials or an API Token.

Use mode 4 when 3x-ui is not installed. Use mode 1 when 3x-ui is already installed.

## Runtime

- Python 3, no third-party Python dependencies.
- 3x-ui installed and available, usually as the `x-ui` service.
- Root privileges, or `sudo`, for system files and service changes.
- Cloudflare API Token scoped to a single zone. Do not use a Global API Key.
- 3x-ui panel credentials or API Token when API mode is used.

## Files

- Script: `xui_cf_deployer.py`
- Deployer config: `/etc/x-ui/cf_deployer_config.json`
- Deployment state: `/etc/x-ui/cf_auto_state.json`
- Subscription snapshot: `cf_auto_last_links.txt` in the current working directory
- Panel access info: `/etc/x-ui/cf_panel_access.json`
- Panel access snapshot: `cf_panel_last_access.txt` in the current working directory
- Panel certificate: `/root/cert/<panel-domain>/`
- acme.sh renewal config: `/root/.acme.sh/`
- Cloudflare IP cache: `/etc/x-ui/cf_cloudflare_ips.json`
- Cloudflare firewall rule state: `/etc/x-ui/cf_firewall_state.json`
- Cloudflare firewall sync service: `/etc/systemd/system/cf-deployer-cloudflare-firewall.service`
- Cloudflare firewall sync timer: `/etc/systemd/system/cf-deployer-cloudflare-firewall.timer`
- Legacy Cloudflare credential file: `/etc/x-ui/cf_account.json`

The deployer no longer uses `/etc/x-ui/cf_account.json`. If that legacy file exists, the script only warns about it.

## x-ui Write Backend

| Condition | Backend |
| --- | --- |
| API Token detected through `x-ui setting -getApiToken` or `XUI_API_TOKEN` | API |
| No API Token and `/etc/x-ui/x-ui.db` exists | Direct SQLite |

Override with `XUI_BACKEND=db` or `XUI_BACKEND=api`.

For 3x-ui v3.0+ direct SQLite writes, the script also handles the `clients` and `client_inbounds` tables and repairs missing historical bindings at startup.

### Optional x-ui Menu Localization

The script can localize the `x-ui` command-line menu. This only changes the terminal menu script, not the web panel.

- It creates a backup at `x-ui.en.bak`.
- Set `XUI_LOCALIZE_MENU=1` to apply localization automatically.
- Set `XUI_LOCALIZE_MENU=0` to skip localization.

The repository stores localization strings as ASCII Unicode escapes so the source tree contains no literal non-English UI text.

## Install and Run

```bash
command -v python3 >/dev/null 2>&1 || (sudo apt update && sudo apt install -y python3)
curl -fsSL -o xui_cf_deployer.py https://raw.githubusercontent.com/thryzx/3x-ui-cf-deployer/main/xui_cf_deployer.py
chmod +x xui_cf_deployer.py
sudo python3 xui_cf_deployer.py
```

Or:

```bash
command -v python3 >/dev/null 2>&1 || (sudo apt update && sudo apt install -y python3)
curl -fsSL -o xui_cf_deployer.py https://raw.githubusercontent.com/thryzx/3x-ui-cf-deployer/main/xui_cf_deployer.py
chmod +x xui_cf_deployer.py
sudo ./xui_cf_deployer.py
```

Optionally set your own subscription generator URL before running:

```bash
export DEPLOYER_CF_URL="https://your-worker.example.workers.dev"
sudo -E ./xui_cf_deployer.py
```

Cloudflare API Token input priority:

- `CF_API_TOKEN`
- `CLOUDFLARE_API_TOKEN`
- hidden interactive prompt

Recommended Cloudflare token permissions:

- `Zone / Zone / Read`
- `Zone / DNS / Edit`
- `Zone / Config Rules / Edit`
- `Zone / Origin Rules / Edit`

If your Cloudflare token page only exposes a generic Rulesets permission, use `Zone / Rulesets / Edit`.

Resource scope:

- `Include -> Specific zone -> your domain`

Notes:

- The deployer itself does not write the Cloudflare Token into `/etc/x-ui`.
- Panel certificates use Cloudflare DNS-01. `acme.sh` stores the scoped token for renewals.
- `Zone Settings:Edit` is no longer required because the script does not change the zone-wide SSL mode.

## Interactive Flow

The script shows a keyboard menu when stdin is interactive:

- Arrow keys, WASD, and HJKL move the cursor.
- Enter confirms the selected mode.
- New servers default to fresh install.
- Servers with 3x-ui already installed default to node deployment.

Set `CFD_PLAIN_MENU=1` to use plain number input in non-interactive environments.

Available modes:

- Deploy nodes
- Uninstall
- Show last subscriptions
- Manage deployed nodes, only shown when a deployment state exists
- Fresh install, only shown when x-ui is not installed
- Show panel access info, only shown when this script installed the panel
- Show x-ui management commands

When run as root for the first time, the script registers the `cfd` shortcut at `/usr/local/bin/cfd`.

### Fresh Install Mode

Use this mode only on a server without 3x-ui.

Flow:

1. Enter node domain, Cloudflare API Token, and protocol selection.
2. Accept or edit the panel domain default: `panel.<root-domain>`.
3. Select a Cloudflare-supported HTTPS panel port automatically: `443/2053/2083/2087/2096/8443`.
4. Create proxied panel DNS and panel hostname SSL Configuration Rule: `strict`.
5. Run the official 3x-ui `install.sh` with SQLite, selected panel port, and installer SSL disabled.
6. Issue the panel certificate with Cloudflare DNS-01 and configure it in 3x-ui.
7. Save panel credentials and access info to `cf_panel_last_access.txt` and `/etc/x-ui/cf_panel_access.json`.
8. Continue with the same node deployment flow as mode 1.

### Deploy Nodes Mode

Prompts:

1. Deployer CF URL, default `https://yx-auto.pages.dev`.
2. Node domain, for example `node.example.com`.
3. Cloudflare API Token.
4. Protocol selection: `1=vless,2=trojan,3=vmess`, comma-separated, empty means all.
5. 3x-ui panel domain, default `panel.<root-domain>`, or `skip`.

Behavior:

- Auto-detects API or direct SQLite backend.
- If a panel domain is configured:
  - Create proxied panel DNS.
  - Switch panel port to a Cloudflare-supported HTTPS port when needed.
  - Open `80/443/panel-port` on active UFW/firewalld setups.
  - Issue and enable a 3x-ui panel HTTPS certificate through Cloudflare DNS-01.
  - Create panel hostname SSL Configuration Rule: `strict`.
- Create proxied node DNS.
- Create node hostname SSL Configuration Rule: `flexible`.
- Create or merge Origin Rules to route paths to selected local ports.
- Open generated node ports for Cloudflare IP ranges only when UFW/firewalld is active. The script fetches Cloudflare's official IP list at runtime, caches successful results, and only uses a bundled fallback if both live fetch and cache are unavailable.
- Install a systemd timer that periodically syncs Cloudflare firewall rules. The sync adds new Cloudflare IP ranges and removes old ranges managed by this script.
- Output subscription links.
- Save subscription output to `cf_auto_last_links.txt`.

The script does not change the Cloudflare zone-wide SSL mode.

### Uninstall Mode

Rollback behavior:

- Delete x-ui inbounds created by the last run.
- Remove managed Origin Rules for the node hostname.
- Remove the node hostname SSL Configuration Rule.
- Remove Cloudflare firewall rules managed by this script. If UFW/firewalld is inactive during uninstall, pending cleanup remains in `/etc/x-ui/cf_firewall_state.json` for the next timer run.
- Restore/delete the node DNS record based on the previous state.
- Remove the local deployment state file.

Legacy state files that contain a zone-wide SSL backup trigger a best-effort global SSL restore.

### Manage Deployed Nodes Mode

Use this mode to delete only selected protocols from the last script-managed deployment, for example deleting VMess while keeping VLESS and Trojan.

Behavior:

- List the deployed protocols, ports, and WebSocket paths from `/etc/x-ui/cf_auto_state.json`.
- Delete only the selected protocol inbounds from 3x-ui.
- Rebuild managed Cloudflare Origin Rules for the remaining protocols.
- Resync Cloudflare-only firewall rules so removed protocol ports are no longer kept open.
- Update `/etc/x-ui/cf_auto_state.json` and `cf_auto_last_links.txt`.

The same action can be run directly:

```bash
cfd --delete-protocol vmess
```

Multiple protocols can be comma-separated, for example `cfd --delete-protocol trojan,vmess`.

### Show Subscriptions Mode

The script first reads `cf_auto_last_links.txt`. If that file is missing, it attempts legacy recovery:

- Rebuild from `domain`, `uuid`, and `routes` in the state file.
- Fallback to reading existing inbounds from SQLite or panel API.

### Show Panel Mode

This mode is only available when this script installed 3x-ui through fresh install mode.

It reads:

- `cf_panel_last_access.txt`
- `/etc/x-ui/cf_panel_access.json`

### x-ui Management Commands

This mode prints common `x-ui` commands and reminds you that:

- `x-ui` opens the 3x-ui command-line menu.
- `cfd` opens this deployer again.

## Subscription Link Parameters

Baseline parameters:

- `epd=yes`
- `epi=yes`
- `egi=no`
- `dkby=yes`

Protocol flags:

- Enabled protocol: `yes`
- Disabled protocol: `no`
- VLESS uses `ev`.
- Trojan uses `et`.
- VMess uses `mess`, matching the current byJoey/yx-auto Worker parameter.

The WebSocket path is URL-encoded into the `path` parameter.

## Troubleshooting

- Zone match failure: check that the domain belongs to the Cloudflare account used by the token.
- 3x-ui API failure: check panel URL, WebBasePath, credentials, or API Token.
- HTTPS certificate error: allow insecure local panel TLS, or use `http://127.0.0.1:<port>`.
- Permission error: run the script with `sudo`.
- Existing last deployment: use uninstall mode first.
- Origin Rules quota reached: the script lists rules and lets you delete selected entries.
- Legacy `/etc/x-ui/cf_account.json`: the script warns about it but does not use it.
- UFW/firewalld enabled: generated node ports are opened for Cloudflare IP ranges only. Your VPS provider security group must still allow those ports. If the official Cloudflare IP list cannot be fetched, the script uses the last cached list before falling back to its bundled bootstrap list.

## Security Boundary

- The panel hostname uses Cloudflare SSL Configuration Rule `strict`, so Cloudflare connects to the VPS origin over HTTPS.
- The node hostname uses `flexible` to match the WebSocket inbounds created by this script with `security=none`.
- Node traffic is not end-to-end TLS. The client-to-Cloudflare leg uses HTTPS/TLS, while the Cloudflare-to-VPS leg is plain WebSocket.
- If you need end-to-end TLS for nodes, the node inbound design must be changed to origin TLS or another transport. This script does not implement that mode.
