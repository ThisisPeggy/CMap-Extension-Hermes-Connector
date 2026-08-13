# Hermes Browser Connector

Local Hermes platform connector for the Hermes Browser Extension. It exposes a
loopback-only authenticated WebSocket and never opens Hermes to the network.

## Install or update

The installer stops the gateway, installs or updates the Connector in place,
asks for the Browser pairing token, and starts the gateway again. Existing Git
checkouts are updated without deleting the plugin directory.

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/ThisisPeggy/hermes-browser-connector/main/install.ps1 | iex
```

### macOS and Linux

```bash
curl -fsSL https://raw.githubusercontent.com/ThisisPeggy/hermes-browser-connector/main/install.sh | sh
```

The Browser extension generates the pairing token. Paste it into the hidden
prompt when the installer asks. To pair manually, use the actual Hermes data
directory for your platform:

- Windows: `%LOCALAPPDATA%\hermes\plugins\hermes-browser\connect.py`
- macOS/Linux: `${HERMES_HOME:-~/.hermes}/plugins/hermes-browser/connect.py`

The connector listens on `127.0.0.1:8765`. The token is stored in Hermes's
`.env` file with private permissions, is carried in the WebSocket subprotocol (not
the URL), and never needs to appear in shell history or process arguments. No
public port or Hermes API key is needed.

## Attachment boundary

The Connector accepts only the explicit `image.attach_bytes` and `file.attach`
RPCs used by the extension. Attachments are base64 data URLs, are capped at
10 MB each (12 files / 50 MB pending per session), and are written only through
Hermes's image and document cache helpers. Image magic bytes and document
extensions are validated before a staged attachment is passed to the existing
Hermes media pipeline. Unknown RPC methods remain blocked.
