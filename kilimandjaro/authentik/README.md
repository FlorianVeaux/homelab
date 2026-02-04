# Authentik Deployment

Self-hosted identity provider with forward authentication support.

## Prerequisites

On the kilimandjaro server, create the required directory structure:

```bash
sudo mkdir -p /nvme/docker/authentik/{database,redis,media,custom-templates,ts/state,ts/config}
```

## Environment Setup

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Edit `.env` and set the following variables:
   - `TS_AUTHKEY`: Generate a reusable auth key from Tailscale admin console with `tag:container`
   - `AUTHENTIK_PG_PASSWORD`: Already generated (or regenerate with `openssl rand -base64 32`)
   - `AUTHENTIK_SECRET_KEY`: Already generated (or regenerate with `openssl rand -base64 60`)

## Deployment

Deploy the Authentik stack:

```bash
docker-compose up -d
```

## Verify Deployment

Check all containers are running:
```bash
docker-compose ps
```

Check Authentik server logs:
```bash
docker-compose logs -f authentik-server
```

Verify Tailscale registration:
```bash
docker exec ts-authentik tailscale status
```

## Access Admin Interface

Once deployed, access the Authentik admin interface via Tailscale:

1. Ensure you're connected to Tailscale VPN
2. Access via Caddy (requires Caddy Caddyfile update): `https://authentik.ts.kilimandjaro.homelab`
3. Or access directly: `http://authentik:9000`

Complete the initial setup wizard to create the admin account.

## Network Architecture

All containers share the Tailscale network namespace via `network_mode: service:ts-authentik`:

- **ts-authentik**: Tailscale sidecar for internal admin access
- **authentik-server**: Web/API server (port 9000)
- **authentik-worker**: Background task processor
- **authentik-db**: PostgreSQL 16 (accessible via localhost:5432)
- **authentik-redis**: Redis cache (accessible via localhost:6379)

## Caddy Integration

To access the admin interface via Tailscale through Caddy, add this to your Caddyfile:

```
authentik.{$HOMELAB_DOMAIN} {
    reverse_proxy ts-authentik:9000
    tls internal
}
```

Then reload Caddy:
```bash
docker exec caddy-proxy caddy reload --config /etc/caddy/Caddyfile
```

## Troubleshooting

Check logs for all services:
```bash
docker-compose logs
```

Check specific service:
```bash
docker-compose logs authentik-server
docker-compose logs authentik-db
```

Restart services:
```bash
docker-compose restart
```
