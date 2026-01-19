# Implementation Plan: Authentik Forward Auth for Mealie

## Overview
Deploy Authentik as a self-hosted identity provider with forward authentication to protect Mealie when exposed to the public internet via florianveaux.fr domain. Authentik admin interface will remain Tailscale-only for security.

## Architecture

### Network Topology
Services will be on BOTH networks for dual access:
- **Tailscale network**: For internal/VPN access (existing behavior)
- **Docker bridge network** (`homelab_public`): For public internet access (new)

```
Public Internet Access (NO Tailscale):
    ↓
mealie.florianveaux.fr (Public DNS)
    ↓
Router Port Forward (443 → Host)
    ↓
Caddy (port 443) [on homelab_public bridge network]
    ↓
Forward Auth Check → Authentik [on homelab_public bridge]
    ↓                       ↓
[Auth OK]              [PostgreSQL + Redis - internal]
    ↓
Mealie [on homelab_public bridge]

Internal Tailscale Access (existing):
    ↓
mealie.ts.kilimandjaro.homelab
    ↓
Caddy (via Tailscale DNS) [on ts-caddy_proxy network]
    ↓
Mealie (via Tailscale DNS) [on ts-mealie network]
```

**Key Change**: Services on both networks means public traffic never touches Tailscale.

## Key Architectural Principles

1. **Dual Network Access**: Services run on BOTH Tailscale (for internal/VPN access) AND Docker bridge (for public access)
2. **No Tailscale on Public Path**: Public users access mealie.florianveaux.fr via pure Docker networking - no Tailscale involvement
3. **Admin Interface Protected**: Authentik admin is ONLY on Tailscale (ts-authentik container) - never exposed publicly
4. **Three Network Layers**:
   - `homelab_public` (Docker bridge): Public-facing services communicate here
   - Tailscale VPN: Internal/admin access continues as before
   - `internal` (Docker bridge): Database and Redis isolated from everything

## Critical Files to Create/Modify

### 1. Create: `/Users/florian.veaux/go/src/github.com/FlorianVeaux/homelab/authentik/docker-compose.yml`
**Purpose**: Deploy Authentik stack with dual network access (Tailscale + Docker bridge)

**Services**:
- `ts-authentik`: Tailscale sidecar (hostname: authentik) - for internal admin access only
- `authentik-db`: PostgreSQL 16 (internal network only)
- `authentik-redis`: Redis (internal network only)
- `authentik-server`: Authentik web/API (exposed on both Tailscale and homelab_public)
- `authentik-worker`: Background task processor

**Network Configuration** (CRITICAL CHANGE):
```yaml
networks:
  homelab_public:
    external: true  # Shared with Caddy and Mealie for public access
  internal:
    driver: bridge
    internal: true  # For database and redis only
```

**Key Configuration**:
- `ts-authentik`: Tailscale network only (for internal admin access)
- `authentik-server` and `authentik-worker`: Connected to BOTH `homelab_public` (for Caddy forward auth) AND `internal` (for database/redis)
- `authentik-db` and `authentik-redis`: Only on `internal` network (not exposed)
- Data volumes: `/nvme/docker/authentik/{database,redis,media,custom-templates,ts/state,ts/config}`
- Required environment variables:
  - `TS_AUTHKEY`: Tailscale auth key (for admin access)
  - `AUTHENTIK_PG_PASSWORD`: PostgreSQL password (generate with `openssl rand -base64 32`)
  - `AUTHENTIK_SECRET_KEY`: Session signing key (generate with `openssl rand -base64 60`)
  - `AUTHENTIK_REDIS__HOST=authentik-redis` (container name, not localhost)
  - `AUTHENTIK_POSTGRESQL__HOST=authentik-db` (container name, not localhost)
- Image versions: `postgres:16-alpine`, `redis:alpine`, `ghcr.io/goauthentik/server:2024.2.1`

**Complete docker-compose.yml structure**:
```yaml
services:
  # Tailscale sidecar - ONLY for internal admin access
  ts-authentik:
    image: tailscale/tailscale:latest
    hostname: authentik
    environment:
      - TS_AUTHKEY=${TS_AUTHKEY}
      - TS_EXTRA_ARGS=--advertise-tags=tag:container
      - TS_STATE_DIR=/var/lib/tailscale
    volumes:
      - /nvme/docker/authentik/ts/state:/var/lib/tailscale
      - /nvme/docker/authentik/ts/config:/config
    devices:
      - /dev/net/tun:/dev/net/tun
    cap_add:
      - net_admin
      - sys_module
    restart: unless-stopped

  authentik-db:
    image: postgres:16-alpine
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -d $${POSTGRES_DB} -U $${POSTGRES_USER}"]
      start_period: 20s
      interval: 30s
      retries: 5
      timeout: 5s
    volumes:
      - /nvme/docker/authentik/database:/var/lib/postgresql/data
    environment:
      - POSTGRES_PASSWORD=${AUTHENTIK_PG_PASSWORD}
      - POSTGRES_USER=authentik
      - POSTGRES_DB=authentik
    networks:
      - internal

  authentik-redis:
    image: redis:alpine
    restart: unless-stopped
    command: --save 60 1 --loglevel warning
    healthcheck:
      test: ["CMD-SHELL", "redis-cli ping | grep PONG"]
      start_period: 20s
      interval: 30s
      retries: 5
      timeout: 3s
    volumes:
      - /nvme/docker/authentik/redis:/data
    networks:
      - internal

  authentik-server:
    image: ghcr.io/goauthentik/server:2024.2.1
    restart: unless-stopped
    command: server
    environment:
      # Database/Redis connection via Docker network (NOT localhost)
      - AUTHENTIK_REDIS__HOST=authentik-redis
      - AUTHENTIK_POSTGRESQL__HOST=authentik-db
      - AUTHENTIK_POSTGRESQL__USER=authentik
      - AUTHENTIK_POSTGRESQL__NAME=authentik
      - AUTHENTIK_POSTGRESQL__PASSWORD=${AUTHENTIK_PG_PASSWORD}
      - AUTHENTIK_SECRET_KEY=${AUTHENTIK_SECRET_KEY}
      - AUTHENTIK_ERROR_REPORTING__ENABLED=false
      - AUTHENTIK_DISABLE_UPDATE_CHECK=true
      - TZ=Europe/Paris
    volumes:
      - /nvme/docker/authentik/media:/media
      - /nvme/docker/authentik/custom-templates:/templates
    ports:
      - "9000:9000"  # For Caddy forward auth on homelab_public network
    networks:
      - homelab_public  # For Caddy forward auth access
      - internal        # For database/redis access
    depends_on:
      - authentik-db
      - authentik-redis

  authentik-worker:
    image: ghcr.io/goauthentik/server:2024.2.1
    restart: unless-stopped
    command: worker
    environment:
      # Same as server
      - AUTHENTIK_REDIS__HOST=authentik-redis
      - AUTHENTIK_POSTGRESQL__HOST=authentik-db
      - AUTHENTIK_POSTGRESQL__USER=authentik
      - AUTHENTIK_POSTGRESQL__NAME=authentik
      - AUTHENTIK_POSTGRESQL__PASSWORD=${AUTHENTIK_PG_PASSWORD}
      - AUTHENTIK_SECRET_KEY=${AUTHENTIK_SECRET_KEY}
      - AUTHENTIK_ERROR_REPORTING__ENABLED=false
      - AUTHENTIK_DISABLE_UPDATE_CHECK=true
      - TZ=Europe/Paris
    volumes:
      - /nvme/docker/authentik/media:/media
      - /nvme/docker/authentik/custom-templates:/templates
      - /var/run/docker.sock:/var/run/docker.sock
    networks:
      - internal
    depends_on:
      - authentik-db
      - authentik-redis

networks:
  homelab_public:
    external: true
  internal:
    driver: bridge
    internal: true
```

### 2. Modify: `/Users/florian.veaux/go/src/github.com/FlorianVeaux/homelab/caddy_proxy/Caddyfile`
**Purpose**: Add forward auth middleware and public Mealie route using Docker networking

**Changes**:
1. Add Authentik internal route (Tailscale-only, for admin access):
   ```
   authentik.{$HOMELAB_DOMAIN} {
       reverse_proxy ts-authentik:9000
       tls internal
   }
   ```

2. Add public Mealie route with forward auth (NO Tailscale - uses Docker bridge network):
   ```
   mealie.florianveaux.fr {
       # Forward auth to Authentik via Docker bridge network
       forward_auth authentik-server:9000 {
           uri /outpost.goauthentik.io/auth/caddy
           copy_headers X-Authentik-Username X-Authentik-Groups X-Authentik-Email X-Authentik-Name X-Authentik-Uid
           header_up X-Original-URL {scheme}://{host}{uri}
       }
       # Proxy to Mealie via Docker bridge network
       reverse_proxy mealie-frontend:3000
       tls contact@florianveaux.fr
   }
   ```

3. Keep existing internal Mealie route unchanged (via Tailscale):
   ```
   mealie.{$HOMELAB_DOMAIN} {
       reverse_proxy mealie.{$TAILNET_DNS}:3001
       tls internal
   }
   ```

**Key Difference**:
- Public route uses Docker service names: `authentik-server:9000` and `mealie-frontend:3000`
- Internal route continues using Tailscale DNS: `mealie.{$TAILNET_DNS}:3001`
- NO Tailscale in public path!

### 3. Modify: `/Users/florian.veaux/go/src/github.com/FlorianVeaux/homelab/caddy_proxy/docker-compose.yml`
**Purpose**: Add Docker bridge network and expose ports for public access

**Changes**:
```yaml
services:
  ts-caddy_proxy:
    image: tailscale/tailscale:latest
    # ... existing Tailscale config ...
    ports:
      - "80:80"    # HTTP (for ACME HTTP-01 challenge)
      - "443:443"  # HTTPS (public access)
    networks:
      - homelab_public  # ADD THIS: ts-caddy_proxy joins homelab_public network

  caddy-proxy:
    image: caddy:2-alpine
    restart: unless-stopped
    network_mode: service:ts-caddy_proxy  # Inherits ALL networks from ts-caddy_proxy
    # ... rest of existing config ...

networks:
  homelab_public:
    external: true
```

**How it works**:
- `ts-caddy_proxy` connects to BOTH Tailscale VPN AND `homelab_public` bridge network
- `caddy-proxy` uses `network_mode: service:ts-caddy_proxy`, so it inherits both networks
- Caddy can now route to both Tailscale services (internal) and Docker bridge services (public)
- Ports 80/443 exposed on `ts-caddy_proxy` are accessible by `caddy-proxy` (shared network namespace)

### 4. Modify: `/Users/florian.veaux/go/src/github.com/FlorianVeaux/homelab/mealie/docker-compose.yml`
**Purpose**: Add Mealie to Docker bridge network for public access

**Changes**:
Add Mealie frontend to `homelab_public` network IN ADDITION to existing Tailscale network:

```yaml
services:
  ts-mealie:
    # ... existing Tailscale config ...
    networks:
      - homelab_public  # ADD THIS

  mealie-frontend:
    # ... existing config ...
    network_mode: service:ts-mealie  # Inherits homelab_public from ts-mealie
    # No other changes needed

  mealie-api:
    # ... existing config ...
    network_mode: service:ts-mealie  # Inherits homelab_public from ts-mealie
    # No other changes needed

networks:
  homelab_public:
    external: true
```

**Result**: Mealie becomes accessible via both Tailscale (internal) and Docker bridge network (public via Caddy)

### 5. Create: Docker Bridge Network
**Purpose**: Shared network for public-facing services (no Tailscale)

**Command**:
```bash
docker network create homelab_public
```

**Verification**:
```bash
docker network ls | grep homelab_public
docker network inspect homelab_public
```

This network must be created BEFORE deploying any services that reference it.

## Implementation Steps

### Phase 0: Create Shared Network (Est. 5 min)

**Step 0.1: Create Docker Bridge Network**
```bash
docker network create homelab_public
```

**Step 0.2: Verify Network Created**
```bash
docker network ls | grep homelab_public
# Should show: homelab_public    bridge    local
```

This network enables Caddy, Authentik, and Mealie to communicate without Tailscale for public access.

### Phase 1: Deploy Authentik (Est. 1-2 hours)

**Step 1.1: Generate Secrets**
```bash
# Generate PostgreSQL password
openssl rand -base64 32

# Generate Authentik secret key
openssl rand -base64 60

# Store securely (not in git) - add to shell environment or secrets manager
```

**Step 1.2: Create Directory Structure**
```bash
mkdir -p /nvme/docker/authentik/{database,redis,media,custom-templates,ts/state,ts/config,certs}
```

**Step 1.3: Set Environment Variables**
```bash
export TS_AUTHKEY="tskey-auth-xxxxxxxxxxxxx"  # From Tailscale admin console
export AUTHENTIK_PG_PASSWORD="<generated_password>"
export AUTHENTIK_SECRET_KEY="<generated_secret>"
```

**Step 1.4: Create docker-compose.yml**
- Create `/Users/florian.veaux/go/src/github.com/FlorianVeaux/homelab/authentik/docker-compose.yml`
- Use configuration from Critical Files section above (full config in agent output)

**Step 1.5: Deploy Authentik**
```bash
cd /Users/florian.veaux/go/src/github.com/FlorianVeaux/homelab/authentik
docker-compose up -d
```

**Step 1.6: Verify Deployment**
```bash
# Check all containers running
docker-compose ps

# Check logs (should see "Authentik fully started")
docker-compose logs -f authentik-server

# Verify Tailscale registration (for internal admin access)
docker exec ts-authentik tailscale status

# Verify Docker bridge network connectivity (CRITICAL for public access)
docker network inspect homelab_public
# Should show authentik-server in "Containers" section

# Test Authentik reachable on Docker bridge network
docker run --rm --network homelab_public alpine wget -O- http://authentik-server:9000/if/flow/initial-setup/
# Should return HTML (not connection error)
```

**Step 1.7: Initial Authentik Setup**
1. Ensure you're connected to Tailscale VPN
2. Access Authentik admin interface via Tailscale: `https://authentik.ts.kilimandjaro.homelab`
   - This routes through ts-authentik container (Tailscale-only, NOT public)
3. Complete initial setup wizard:
   - Create admin account (strong password)
   - Configure default flows (use defaults)
   - Skip email configuration for now

**Important**: Authentik admin interface is ONLY accessible via Tailscale, never from public internet. Public users only interact with the login page (via forward auth).

### Phase 2: Configure Authentik Forward Auth (Est. 30 min)

**Step 2.1: Create Proxy Provider**
1. Navigate to **Admin Interface** → **Applications** → **Providers**
2. Click **Create** → Select **Proxy Provider**
3. Configure:
   - Name: `Mealie Forward Auth`
   - Authorization flow: `default-provider-authorization-implicit-consent`
   - Type: `Forward auth (single application)`
   - External host: `https://mealie.florianveaux.fr`
   - Internal host: `http://mealie-frontend:3000` (Docker bridge network, NOT Tailscale)
   - Token validity: `hours=24`
4. Save

**Step 2.2: Create Application**
1. Navigate to **Applications** → **Applications**
2. Click **Create**
3. Configure:
   - Name: `Mealie`
   - Slug: `mealie`
   - Provider: Select `Mealie Forward Auth`
   - Launch URL: `https://mealie.florianveaux.fr`
4. Save

**Note**: No separate outpost container needed - Authentik server handles forward auth requests directly

### Phase 3: Configure Caddy and Mealie (Est. 30 min)

**Step 3.1: Update Mealie docker-compose.yml**
- Modify `/Users/florian.veaux/go/src/github.com/FlorianVeaux/homelab/mealie/docker-compose.yml`
- Add `homelab_public` network to `ts-mealie` service
- See Critical Files section for details

**Step 3.2: Restart Mealie**
```bash
cd /Users/florian.veaux/go/src/github.com/FlorianVeaux/homelab/mealie
docker-compose up -d
```

**Step 3.3: Verify Mealie on Bridge Network**
```bash
docker network inspect homelab_public
# Should show ts-mealie in "Containers" section

# Test Mealie reachable on Docker bridge network
docker run --rm --network homelab_public alpine wget -O- http://mealie-frontend:3000
# Should return HTML (not connection error)
```

**Step 3.4: Update Caddy Caddyfile**
- Modify `/Users/florian.veaux/go/src/github.com/FlorianVeaux/homelab/caddy_proxy/Caddyfile`
- Add routes as specified in Critical Files section above
- Use Docker service names (`authentik-server:9000`, `mealie-frontend:3000`) for public routes

**Step 3.5: Update Caddy docker-compose.yml**
- Modify `/Users/florian.veaux/go/src/github.com/FlorianVeaux/homelab/caddy_proxy/docker-compose.yml`
- Add `homelab_public` network to `ts-caddy_proxy` service
- Add port exposures (80, 443) to `ts-caddy_proxy` service

**Step 3.6: Restart Caddy**
```bash
cd /Users/florian.veaux/go/src/github.com/FlorianVeaux/homelab/caddy_proxy
docker-compose up -d
docker exec caddy-proxy caddy reload --config /etc/caddy/Caddyfile
```

**Step 3.7: Verify Caddy Configuration**
```bash
# Check Caddy logs for errors
docker logs caddy-proxy

# Verify Caddy on homelab_public network
docker network inspect homelab_public | grep caddy

# Test forward auth endpoint reachable from Caddy via Docker bridge
docker exec caddy-proxy wget -O- http://authentik-server:9000/outpost.goauthentik.io/auth/caddy
# Should return 403 or redirect (not 404 or "could not resolve")

# Test Mealie reachable from Caddy via Docker bridge
docker exec caddy-proxy wget -O- http://mealie-frontend:3000
# Should return HTML
```

### Phase 4: Configure DNS and Network (Est. 30 min)

**Step 4.1: Update DNS**
1. Log in to DNS provider for florianveaux.fr
2. Add A record:
   ```
   mealie.florianveaux.fr  A  <your_public_ip>
   ```
3. Wait for DNS propagation (check with `nslookup mealie.florianveaux.fr`)

**Step 4.2: Configure Router Port Forwarding**
1. Access router admin interface
2. Add port forwarding rules:
   - External Port 443 (TCP) → Internal IP: `<host_machine_ip>`:443
   - External Port 80 (TCP) → Internal IP: `<host_machine_ip>`:80
3. Find host machine IP: `hostname -I` or check router's DHCP client list
4. Ports on host bind to Docker containers via port mapping in docker-compose.yml

**Step 4.3: Verify Port Forwarding**
```bash
# From external network (mobile hotspot, VPS, etc.)
curl -I https://mealie.florianveaux.fr
# Should see response (even if redirect), not timeout
```

### Phase 5: End-to-End Testing (Est. 30 min)

**Test 1: Unauthenticated Access**
- Action: Open incognito browser, navigate to `https://mealie.florianveaux.fr`
- Expected: Redirect to Authentik login page
- URL should show Authentik domain

**Test 2: Valid Authentication**
- Action: Log in with Authentik admin credentials
- Expected: Redirect back to Mealie, full access granted
- Mealie dashboard should load completely

**Test 3: Session Persistence**
- Action: Close browser, reopen, navigate to `https://mealie.florianveaux.fr`
- Expected: Direct access without re-login (session cookie valid)

**Test 4: Logout**
- Action: Access Authentik user menu (top right) → Sign out
- Then try accessing `https://mealie.florianveaux.fr`
- Expected: Redirect to login page

**Test 5: Tailscale Access (Unchanged)**
- Action: Via Tailscale, access `https://mealie.ts.kilimandjaro.homelab`
- Expected: Direct access, no Authentik authentication prompt
- This confirms internal routes still work

**Test 6: TLS Certificate**
- Action: Check certificate in browser (click padlock icon)
- Expected: Valid Let's Encrypt certificate for mealie.florianveaux.fr
- No certificate warnings

## Troubleshooting

### Issue: Infinite Redirect Loop
**Symptoms**: Browser redirects between Mealie and Authentik repeatedly

**Solutions**:
1. Verify `X-Original-URL` header in Caddyfile: `header_up X-Original-URL {scheme}://{host}{uri}`
2. Check Authentik provider external host matches: `https://mealie.florianveaux.fr`
3. Check browser cookies - ensure `authentik_session` cookie set for correct domain
4. Check Authentik logs: `docker logs authentik-server`

### Issue: Forward Auth Returns 404 or "Could Not Resolve"
**Symptoms**: 404 error or DNS resolution error when accessing protected service

**Solutions**:
1. Verify Authentik on homelab_public network:
   ```bash
   docker network inspect homelab_public | grep authentik-server
   # Should show authentik-server container
   ```
2. Verify Caddy on homelab_public network:
   ```bash
   docker network inspect homelab_public | grep caddy
   # Should show ts-caddy_proxy container
   ```
3. Test Authentik reachability from Caddy via Docker bridge:
   ```bash
   docker exec caddy-proxy wget -O- http://authentik-server:9000/outpost.goauthentik.io/auth/caddy
   # Should NOT return "could not resolve host" or connection refused
   ```
4. Verify endpoint URI in Caddyfile: `/outpost.goauthentik.io/auth/caddy`
5. Verify Authentik application and provider created correctly
6. Check Authentik logs: `docker logs authentik-server | grep -i error`

### Issue: TLS Certificate Error
**Symptoms**: Browser shows "Your connection is not private"

**Solutions**:
1. Verify DNS resolves: `nslookup mealie.florianveaux.fr`
2. Verify port 80 accessible (Let's Encrypt uses HTTP-01 challenge)
3. Check Caddy logs: `docker logs caddy-proxy | grep -i acme`
4. Wait a few minutes - certificate issuance can take time
5. Check email (`contact@florianveaux.fr`) for Let's Encrypt notifications

### Issue: Can't Access Authentik Admin
**Symptoms**: Cannot reach Authentik interface via Tailscale at `https://authentik.ts.kilimandjaro.homelab`

**Solutions**:
1. Verify you're connected to Tailscale VPN:
   ```bash
   tailscale status
   ```
2. Verify ts-authentik container running:
   ```bash
   docker ps | grep ts-authentik
   docker exec ts-authentik tailscale status
   ```
3. Check Caddy Caddyfile has Authentik route:
   ```bash
   grep "authentik.{$HOMELAB_DOMAIN}" /Users/florian.veaux/go/src/github.com/FlorianVeaux/homelab/caddy_proxy/Caddyfile
   # Should show: reverse_proxy ts-authentik:9000
   ```
4. Try accessing directly via ts-authentik hostname:
   ```bash
   curl http://ts-authentik:9000  # From within Caddy container
   ```

## Security Considerations

### Secrets Management
- **NEVER commit secrets to git**: Store in environment variables or secrets manager
- **Secret rotation**: Plan to rotate `AUTHENTIK_SECRET_KEY` and `AUTHENTIK_PG_PASSWORD` periodically
- **Backup secrets securely**: Store encrypted backup of environment variables

### Database Security
- PostgreSQL only accessible via internal Docker network (isolated from public and Tailscale)
- Database not exposed on homelab_public network (only authentik-server and authentik-worker can access)
- Strong password generated with `openssl rand`
- Regular backups recommended:
  ```bash
  docker exec authentik-db pg_dump -U authentik authentik > backup-$(date +%Y%m%d).sql
  ```

### Network Isolation
- **Three-layer network architecture**:
  1. **Public layer** (`homelab_public` bridge): Caddy, Authentik forward auth endpoint, Mealie frontend
  2. **Tailscale layer**: Internal/admin access via VPN (Caddy, Authentik admin, Mealie)
  3. **Internal layer**: Database and Redis (completely isolated)
- Authentik admin interface: Tailscale-only (not exposed to public)
- Database and Redis: Internal network only (no external or public access)
- Caddy: Only service with public ports exposed (80, 443)
- Public access path: NEVER touches Tailscale (uses Docker bridge only)

### Session Security
- Default token validity: 24 hours (configurable in Provider settings)
- Cookies: Automatically set with `Secure`, `HttpOnly`, `SameSite=Lax` attributes
- MFA: Can be enabled later if needed

### Monitoring
- Watch Authentik event logs: **Admin Interface** → **Events** → **Logs**
- Monitor failed login attempts
- Set up Caddy access logging for public routes
- Consider rate limiting for login endpoint (future enhancement)

## Backup Strategy

### Critical Data
1. **PostgreSQL database**: User accounts, policies, configuration
2. **Authentik media**: Custom templates, icons
3. **Environment variables**: Secrets (encrypted storage)

### Backup Script
```bash
#!/bin/bash
BACKUP_DIR="/nvme/docker/backups/authentik/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup database
docker exec authentik-db pg_dump -U authentik authentik | gzip > "$BACKUP_DIR/authentik-db.sql.gz"

# Backup media files
tar -czf "$BACKUP_DIR/authentik-media.tar.gz" -C /nvme/docker/authentik media

# Backup environment variables (encrypt this file!)
echo "AUTHENTIK_PG_PASSWORD=${AUTHENTIK_PG_PASSWORD}" > "$BACKUP_DIR/.env"
echo "AUTHENTIK_SECRET_KEY=${AUTHENTIK_SECRET_KEY}" >> "$BACKUP_DIR/.env"
chmod 600 "$BACKUP_DIR/.env"

echo "Backup completed: $BACKUP_DIR"
```

Run weekly via cron: `0 2 * * 0 /path/to/backup-authentik.sh`

## Future Enhancements

### Phase 2: Expand to Other Services
Once Mealie is working, easily protect additional services:
1. Add Caddy route with forward auth snippet
2. Create Authentik application for service
3. Update DNS (servicename.florianveaux.fr)
4. Test access

**Good candidates**: Nextcloud, Portainer, Heimdall, AdGuard Home

### Phase 3: Add MFA
Enable multi-factor authentication for enhanced security:
1. **Admin Interface** → **Flows & Stages** → **Stages**
2. Create **Authenticator Validation Stage** (TOTP)
3. Add to **Default Authentication Flow**
4. Users enroll via user settings (QR code scan)

Supports: TOTP (Google Authenticator, Authy), WebAuthn (Yubikey, Touch ID), Duo

### Phase 4: OIDC/SAML Integration
Configure Authentik as OIDC provider for native SSO:
- Nextcloud: OIDC integration (eliminates double-login)
- Portainer: OIDC authentication
- Other homelab services with OIDC support

### Phase 5: External Identity Providers
Allow login via Google, GitHub, Microsoft:
- **Admin Interface** → **Directory** → **Federation & Social login**
- Create OAuth2 sources for external providers
- Users can choose authentication method at login

## Success Criteria

Implementation successful when:
- ✅ Authentik deployed and accessible via `https://authentik.ts.kilimandjaro.homelab`
- ✅ Mealie accessible publicly at `https://mealie.florianveaux.fr`
- ✅ Unauthenticated users redirected to Authentik login page
- ✅ Authenticated users access Mealie successfully
- ✅ Session persists across browser restarts (within 24 hours)
- ✅ Tailscale-only route (`https://mealie.ts.kilimandjaro.homelab`) still works without auth
- ✅ Let's Encrypt certificate valid for `mealie.florianveaux.fr`
- ✅ Logout functionality works correctly

## Rollback Plan

If issues arise, rollback steps:

1. **Disable public Mealie route**:
   - Comment out `mealie.florianveaux.fr` block in Caddyfile
   - Reload Caddy: `docker exec caddy-proxy caddy reload --config /etc/caddy/Caddyfile`

2. **Stop Authentik**:
   ```bash
   cd /Users/florian.veaux/go/src/github.com/FlorianVeaux/homelab/authentik
   docker-compose down
   ```

3. **Remove port forwarding**:
   - Delete router port forwarding rules (443, 80)

4. **Revert Caddy changes**:
   - Restore original Caddyfile from git: `git checkout caddy_proxy/Caddyfile`
   - Restore original docker-compose.yml: `git checkout caddy_proxy/docker-compose.yml`
   - Reload Caddy

Mealie will remain accessible via Tailscale only (original configuration).

## Estimated Timeline

- **Phase 1**: Deploy Authentik - 1-2 hours
- **Phase 2**: Configure Authentik - 30 minutes
- **Phase 3**: Configure Caddy - 30 minutes
- **Phase 4**: DNS and Network - 30 minutes
- **Phase 5**: Testing - 30 minutes

**Total**: 3-4 hours for initial setup

## Notes

- Keep Authentik version pinned (`2024.2.1`) initially, upgrade after validating stability
- Document any deviations from plan in homelab wiki/README
- Test from multiple networks (home, mobile, external VPS) to verify public access
- Consider setting up monitoring/alerting for Authentik service health
