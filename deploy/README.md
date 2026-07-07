# Deploying wiskill

Runs as a container from the public image `ghcr.io/semlix/wiskill`, behind the
host's existing Caddy, at `https://wiskill.barrahome.org`.

## One-time setup on the server

```bash
mkdir -p /home/alberto/wiskill/data/pages
cd /home/alberto/wiskill
cp <this repo>/deploy/docker-compose.yml .
cp <this repo>/deploy/wiskill.toml .
cp <this repo>/deploy/.env.example .env      # then edit: set WISKILL_SECRET, WISKILL_TAG
```

Ship your notes (source of truth) from your machine:

```bash
rsync -av ~/wiskill/data/pages/ alberto@app.openremedy.io:/home/alberto/wiskill/data/pages/
```

Start it (the index builds on first run):

```bash
docker compose -p wiskill up -d
docker compose -p wiskill logs -f wiskill     # watch startup / reindex
```

Bootstrap an admin user and an API key (used by the web/API and the MCP header):

```bash
docker compose -p wiskill exec wiskill wiskill --config /app/wiskill.toml user add me --role admin --password 'CHANGE-ME'
docker compose -p wiskill exec wiskill wiskill --config /app/wiskill.toml apikey add llm --role editor
```

## Caddy

Add to the OpenRemedy Caddyfile (`/home/alberto/openremedy-deployment/docker/Caddyfile`):

```
wiskill.barrahome.org {
    reverse_proxy wiskill:8000
}
```

Reload: `docker compose -p openremedy exec caddy caddy reload --config /etc/caddy/Caddyfile`

## Cloudflare (manual)

- DNS: `wiskill.barrahome.org` → server IP.
- SSL/TLS mode "Full". If the orange-cloud proxy blocks Let's Encrypt issuance,
  install a Cloudflare **Origin Certificate** and add a `tls` directive to the
  Caddy block.

## Upgrade to a new version

```bash
cd /home/alberto/wiskill
sed -i 's/^WISKILL_TAG=.*/WISKILL_TAG=X.Y.Z/' .env
docker compose -p wiskill pull && docker compose -p wiskill up -d
```

## MCP client (Claude Code)

```bash
claude mcp add --transport http --header "Authorization: Bearer <editor-key>" \
  wiskill https://wiskill.barrahome.org/mcp/
```

## Smoke test

```bash
curl -sI https://wiskill.barrahome.org/login | head -1                 # 200
curl -s -o /dev/null -w '%{http_code}\n' https://wiskill.barrahome.org/api/pages    # 401
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://wiskill.barrahome.org/mcp/ # 401
```
