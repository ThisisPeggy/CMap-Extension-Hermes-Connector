# Hermes Browser Connector

Local Hermes platform connector for the Hermes Browser Extension. It exposes a
loopback-only authenticated WebSocket and never opens Hermes to the network.

## Install

```bash
hermes plugins install https://github.com/ThisisPeggy/hermes-browser-connector --enable
```

The Browser extension generates the pairing command. Run it once, then restart
the gateway:

```bash
python3 ~/.hermes/plugins/hermes-browser/connect.py --token <PAIRING_TOKEN>
hermes gateway restart
```

The connector listens on `127.0.0.1:8765`. The token is stored in
`~/.hermes/.env` with mode `0600`. No public port or Hermes API key is needed.

