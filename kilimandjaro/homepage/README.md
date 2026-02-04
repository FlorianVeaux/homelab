# Homepage Configuration

This directory contains the configuration for the Homepage dashboard service.

## Configuration Files

- **`config/settings.yaml`** - Layout, theme, and general settings
- **`config/services.yaml`** - Service definitions with widgets and links
- **`config/widgets.yaml`** - Information widgets (search, resources, datetime)
- **`config/docker.yaml`** - Docker socket configuration
- **`config/.env.example`** - Template for environment variables

## Setup Instructions

### 1. Create Environment File

Copy the example environment file and fill in your API keys:

```bash
cp config/.env.example config/.env
# Edit config/.env with your actual credentials
```

### 2. Generate API Keys

You'll need to generate API keys for the following services:

#### Immich API Key
1. Log into Immich at https://immich.florianveaux.fr
2. Go to Settings > API Keys
3. Click "Create API Key"
4. Copy the key to `HOMEPAGE_VAR_IMMICH_API_KEY` in `.env`

#### Portainer API Key
1. Log into Portainer at https://portainer.fmaison
2. Go to User settings (click your username)
3. Scroll to "Access tokens"
4. Click "Add access token"
5. Copy the key to `HOMEPAGE_VAR_PORTAINER_API_KEY` in `.env`

#### Authentik API Key
1. Log into Authentik at https://auth.florianveaux.fr
2. Go to Admin interface > Tokens & App passwords
3. Create a new token with read permissions
4. Copy the key to `HOMEPAGE_VAR_AUTHENTIK_API_KEY` in `.env`

#### Nextcloud App Password
1. Log into Nextcloud at https://nextcloud.florianveaux.fr
2. Go to Settings > Security
3. Create a new app password
4. Copy username and password to `.env`

#### AdGuard Home Credentials
Use your existing AdGuard Home login credentials.

### 3. Update Docker Compose

Make sure your `docker-compose.yml` mounts the config directory and loads the `.env` file:

```yaml
services:
  homepage:
    image: ghcr.io/gethomepage/homepage:latest
    container_name: homepage
    restart: unless-stopped
    ports:
      - "3000:3000"
    volumes:
      - ./config:/app/config
      - /var/run/docker.sock:/var/run/docker.sock:ro
    env_file:
      - ./config/.env
    environment:
      - PUID=1000
      - PGID=1000
    networks:
      - caddy_public
```

### 4. Restart Homepage

```bash
cd /path/to/homelab/kilimandjaro/homepage
docker compose down
docker compose up -d
```

## Customization

### Adding New Services

Edit `config/services.yaml` and add your service under the appropriate group:

```yaml
- Group Name:
    - Service Name:
        icon: service-icon.png
        href: https://service.url
        description: Service description
        siteMonitor: https://service.url
        widget:
          type: service-type
          url: https://service.url
          key: {{HOMEPAGE_VAR_SERVICE_API_KEY}}
```

### Changing Theme

Edit `config/settings.yaml`:

```yaml
theme: dark  # or light
color: slate  # or: blue, green, red, purple, etc.
```

### Adding Weather Widget

Uncomment the weather section in `config/widgets.yaml` and add your coordinates:

```yaml
- openmeteo:
    label: Home
    latitude: YOUR_LATITUDE
    longitude: YOUR_LONGITUDE
    timezone: YOUR_TIMEZONE
    units: metric
```

## Widget Support

The following services have native widget support in Homepage:

- ✅ **Immich** - Shows photos, videos, storage usage
- ✅ **Nextcloud** - Shows storage, users, files count
- ✅ **Portainer** - Shows containers, CPU, memory
- ✅ **AdGuard Home** - Shows queries, blocked ads, filtering status
- ✅ **Authentik** - Shows users, groups, applications
- ⚠️ **Flood** - Limited support, may need custom API
- ⚠️ **Backrest** - May need custom API widget
- ⚠️ **Mealie** - May need custom API widget

For services without native widgets, they'll still appear as clickable cards with site monitoring.

## Troubleshooting

### Widgets Not Showing Data

1. Check API keys are correct in `.env`
2. Verify services are accessible from Homepage container
3. Check Homepage logs: `docker logs homepage`
4. Ensure internal `.fmaison` domains are accessible from the container

### Site Monitor Failing

If internal services (`.fmaison`) aren't accessible, you may need to:

1. Add Homepage to the same Docker network as Caddy
2. Configure Homepage's network to access internal DNS
3. Or remove `siteMonitor` for internal services

## Resources

- [Homepage Documentation](https://gethomepage.dev/)
- [Service Widgets](https://gethomepage.dev/configs/services/)
- [Info Widgets](https://gethomepage.dev/configs/info-widgets/)
- [Settings Reference](https://gethomepage.dev/configs/settings/)
