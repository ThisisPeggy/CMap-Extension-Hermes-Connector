# Hermes Browser Connector

Local Hermes platform connector for the Hermes Browser Extension. It exposes a
loopback-only authenticated WebSocket and never opens Hermes to the network.

## Install

```bash
hermes plugins install https://github.com/ThisisPeggy/hermes-browser-connector --enable --force
```

`--force` makes the same command work for both a first install and an update of
an existing Connector. The Browser extension generates a pairing token. Run
the setup command once, then paste the token into the hidden prompt:

```bash
python3 ~/.hermes/plugins/hermes-browser/connect.py
hermes gateway restart
```

The connector listens on `127.0.0.1:8765`. The token is stored in
`~/.hermes/.env` with mode `0600`, is carried in the WebSocket subprotocol (not
the URL), and never needs to appear in shell history or process arguments. No
public port or Hermes API key is needed.
