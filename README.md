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
- Added subscription node label parameters for flag, country code, optional base name override, and per-protocol sequence numbers.
- Added an `ALL` subscription link while keeping per-protocol links for diagnostics.
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
5. Node flag emoji, default US flag, or `skip`.
6. Country code, default `US`.
7. Node base name, optional. Empty keeps the current Worker default node name.
8. 3x-ui panel domain, default `panel.<root-domain>`, or `skip`.

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
- Output `ALL` subscription first, then selected per-protocol subscriptions.
- Save subscription output to `cf_auto_last_links.txt`.

The script does not change the Cloudflare zone-wide SSL mode.

### Uninstall Mode

Rollback behavior:

- Delete x-ui inbounds created by the last run.
- Remove managed Origin Rules for the node hostname.
- Remove the node hostname SSL Configuration Rule.
- Restore/delete the node DNS record based on the previous state.
- Remove the local deployment state file.

Legacy state files that contain a zone-wide SSL backup trigger a best-effort global SSL restore.

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

The WebSocket path is URL-encoded into the `path` parameter for per-protocol links.

Node label parameters:

- `nf`: node flag. This may contain a flag emoji at runtime.
- `cc`: country code, for example `US`.
- `nn`: optional base name override. If omitted, the Worker keeps its existing default node name.

The Worker should format generated client node names as:

```text
<flag>[US][VLESS] <base name> - 01
```

The sequence number is counted per protocol. If a protocol produces only one final node, the Worker should omit the ` - 01` suffix.

Aggregate subscription parameters:

- `ALL` links enable all selected protocols in one subscription URL.
- `vlp`: VLESS WebSocket path.
- `trp`: Trojan WebSocket path.
- `vmp`: VMess WebSocket path.
- `path`: fallback path for older Worker behavior and single-protocol links.
- VMess compatibility: links include both `mess` and `evm`.

The stock `byJoey/yx-auto` Worker must be adapted before the `ALL` link can safely mix protocols with different paths. Per-protocol links keep working with the old single `path` behavior.

## yx-auto Worker Compatibility

Patch your `_worker.js` so it reads the extra parameters, keeps one path per protocol, and renames nodes after all links for each protocol are collected.

In the subscription route parser, make VMess accept both parameter names and pass path and label maps:

```js
const vmEnabled = url.searchParams.get('mess') === 'yes' || url.searchParams.get('evm') === 'yes';
const customPath = url.searchParams.get('path') || '/';
const pathMap = {
  vless: url.searchParams.get('vlp') || customPath,
  trojan: url.searchParams.get('trp') || customPath,
  vmess: url.searchParams.get('vmp') || customPath,
};
const nodeLabel = {
  flag: url.searchParams.get('nf') || '',
  country: url.searchParams.get('cc') || '',
  name: url.searchParams.get('nn') || '',
};

return await handleSubscriptionRequest(
  request,
  uuid,
  domain,
  piu,
  ipv4Enabled,
  ipv6Enabled,
  ispMobile,
  ispUnicom,
  ispTelecom,
  evEnabled,
  etEnabled,
  vmEnabled,
  disableNonTLS,
  pathMap,
  echConfig,
  nodeLabel
);
```

Add these helpers before `handleSubscriptionRequest`:

```js
function b64EncodeUnicode(value) {
  const bytes = new TextEncoder().encode(value);
  let binary = '';
  bytes.forEach(byte => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary);
}

function b64DecodeUnicode(value) {
  const binary = atob(value);
  const bytes = Uint8Array.from(binary, char => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

function formatNodeName(baseName, protocol, nodeLabel, index, total) {
  const label = nodeLabel || {};
  const base = String(label.name || baseName || protocol).trim();
  const flag = String(label.flag || '').trim();
  const country = String(label.country || '').trim().toUpperCase();
  const prefix = `${flag}${country ? `[${country}]` : ''}[${protocol}]`;
  const suffix = total > 1 ? ` - ${String(index + 1).padStart(2, '0')}` : '';
  return `${prefix} ${base}${suffix}`.trim();
}

function renamePlainNodeLink(link, protocol, nodeLabel, index, total) {
  const marker = link.lastIndexOf('#');
  const baseName = marker >= 0 ? decodeURIComponent(link.slice(marker + 1)) : protocol;
  const newName = encodeURIComponent(formatNodeName(baseName, protocol, nodeLabel, index, total));
  return marker >= 0 ? `${link.slice(0, marker + 1)}${newName}` : `${link}#${newName}`;
}

function renameVmessNodeLink(link, protocol, nodeLabel, index, total) {
  const prefix = 'vmess://';
  if (!link.startsWith(prefix)) return link;
  const config = JSON.parse(b64DecodeUnicode(link.slice(prefix.length)));
  config.ps = formatNodeName(config.ps || protocol, protocol, nodeLabel, index, total);
  return `${prefix}${b64EncodeUnicode(JSON.stringify(config))}`;
}

function renameProtocolLinks(links, protocol, nodeLabel) {
  const total = links.length;
  return links.map((link, index) => {
    if (protocol === 'VMESS') {
      return renameVmessNodeLink(link, protocol, nodeLabel, index, total);
    }
    return renamePlainNodeLink(link, protocol, nodeLabel, index, total);
  });
}
```

Change `handleSubscriptionRequest` to accept `nodeLabel`, normalize `customPath` into a path map, collect links per protocol, and rename once at the end:

```js
async function handleSubscriptionRequest(
  request,
  user,
  customDomain,
  piu,
  ipv4Enabled,
  ipv6Enabled,
  ispMobile,
  ispUnicom,
  ispTelecom,
  evEnabled,
  etEnabled,
  vmEnabled,
  disableNonTLS,
  customPath,
  echConfig = null,
  nodeLabel = null
) {
  const pathMap = typeof customPath === 'object' && customPath !== null
    ? customPath
    : { vless: customPath || '/', trojan: customPath || '/', vmess: customPath || '/' };
  const protocolLinks = { VLESS: [], TROJAN: [], VMESS: [] };
  const addProtocolLinks = (protocol, links) => {
    protocolLinks[protocol].push(...links);
  };

  // Replace direct finalLinks.push calls:
  // VLESS: addProtocolLinks('VLESS', generateLinksFromSource(list, user, nodeDomain, disableNonTLS, pathMap.vless, echConfig));
  // Trojan: addProtocolLinks('TROJAN', await generateTrojanLinksFromSource(list, user, nodeDomain, disableNonTLS, pathMap.trojan, echConfig));
  // VMess: addProtocolLinks('VMESS', generateVMessLinksFromSource(list, user, nodeDomain, disableNonTLS, pathMap.vmess, echConfig));
  // New IP VLESS branches should also use pathMap.vless.

  finalLinks.push(...renameProtocolLinks(protocolLinks.VLESS, 'VLESS', nodeLabel));
  finalLinks.push(...renameProtocolLinks(protocolLinks.TROJAN, 'TROJAN', nodeLabel));
  finalLinks.push(...renameProtocolLinks(protocolLinks.VMESS, 'VMESS', nodeLabel));
}
```

The last snippet shows the required edit pattern. Keep the rest of the original response formatting, fallback error node, and target conversion logic in place.

## Troubleshooting

- Zone match failure: check that the domain belongs to the Cloudflare account used by the token.
- 3x-ui API failure: check panel URL, WebBasePath, credentials, or API Token.
- HTTPS certificate error: allow insecure local panel TLS, or use `http://127.0.0.1:<port>`.
- Permission error: run the script with `sudo`.
- Existing last deployment: use uninstall mode first.
- Origin Rules quota reached: the script lists rules and lets you delete selected entries.
- Legacy `/etc/x-ui/cf_account.json`: the script warns about it but does not use it.

## Security Boundary

- The panel hostname uses Cloudflare SSL Configuration Rule `strict`, so Cloudflare connects to the VPS origin over HTTPS.
- The node hostname uses `flexible` to match the WebSocket inbounds created by this script with `security=none`.
- Node traffic is not end-to-end TLS. The client-to-Cloudflare leg uses HTTPS/TLS, while the Cloudflare-to-VPS leg is plain WebSocket.
- If you need end-to-end TLS for nodes, the node inbound design must be changed to origin TLS or another transport. This script does not implement that mode.
