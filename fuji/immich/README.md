# Immich with Authentik Authentication

This document explains how Immich is configured with Authentik for authentication, including the workaround for the mobile app.

## Architecture

Immich is exposed publicly at `https://immich.florianveaux.fr` with two layers of authentication:

1. **Forward Auth (Caddy + Authentik)**: Protects the entire domain with a proxy authentication layer
2. **OAuth2 (Immich + Authentik)**: Native Immich authentication using Authentik as the OAuth2 provider

This dual setup works perfectly in browsers but causes issues with the Immich mobile app.

## The Mobile App Problem

The Immich mobile app cannot handle the "splash screen" login from Forward Auth. The app expects to connect directly to the Immich API without an intermediate authentication step.

## Solution: HTTP Basic Auth Bypass

We use HTTP Basic Authentication with a dedicated service account to bypass the Forward Auth layer for the mobile app.

**Reference**: [Immich Discussion #3118](https://github.com/immich-app/immich/discussions/3118#discussioncomment-13973618)

### Security Model

- A **service account** is created in Authentik (not a regular user account)
- This service account is **only authorized to access Immich** (no other services)
- Credentials are base64-encoded and stored in the mobile app
- The Forward Auth provider accepts HTTP Basic Authentication as an alternative to session-based auth

---

## Setup Instructions

### Step 1: Create Service Account in Authentik

1. Log into Authentik at `https://auth.florianveaux.fr`
2. Go to **Directory** → **Users**
3. Click **Create** → **Create Service Account**
4. Configure the service account:
   - **Username**: `immich-mobile-service` (or any name you prefer)
   - **Name**: `Immich Mobile App Service Account`
   - **Save** and note the generated password

### Step 2: Restrict Service Account to Immich Only

1. Go to **Applications** → **Applications**
2. Click on your **Immich** application
3. Click **Edit**
4. Under **Policy / Group / User Bindings**, add a policy that:
   - Grants access to the `immich-mobile-service` service account
   - Denies access to all other applications for this service account

Alternatively, create a dedicated group:
1. Go to **Directory** → **Groups** → **Create**
2. Name: `immich-mobile-users`
3. Add the service account to this group
4. In the Immich application, bind this group with appropriate access

### Step 3: Configure Authentik Forward Auth Provider

The Forward Auth provider must be configured to accept HTTP Basic Authentication:

1. Go to **Applications** → **Providers**
2. Click on your **Immich Forward Auth** provider
3. Ensure the provider is configured to accept Basic Authentication:
   - Under **Advanced protocol settings**, verify that HTTP Basic Auth is enabled
   - The provider should validate credentials against Authentik's user directory

> **Note**: Authentik's Proxy Provider supports HTTP Basic Auth by default. When a request includes an `Authorization: Basic ...` header, Authentik validates the credentials before allowing the request through.

### Step 4: Generate Base64 Credentials

On your local machine (or any Unix system):

```bash
echo -n 'immich-mobile-service:YOUR_SERVICE_ACCOUNT_PASSWORD' | base64
```

This will output a base64 string like: `aW1taWNoLW1vYmlsZS1zZXJ2aWNlOnlvdXJwYXNzd29yZA==`

**Important**: Replace `YOUR_SERVICE_ACCOUNT_PASSWORD` with the actual password from Step 1.

### Step 5: Configure Immich Mobile App

1. Open the Immich mobile app
2. Tap the **Settings** icon (gear)
3. Navigate to **Advanced** → **Custom proxy headers**
4. Add a new header:
   - **Header name**: `Authorization`
   - **Header value**: `Basic aW1taWNoLW1vYmlsZS1zZXJ2aWNlOnlvdXJwYXNzd29yZA==` (use your generated base64 string)
5. Save the configuration
6. Try connecting to your Immich server at `https://immich.florianveaux.fr`

---

## How It Works

1. Mobile app makes a request to `https://immich.florianveaux.fr`
2. Caddy intercepts and sends to Authentik Forward Auth at `/outpost.goauthentik.io/auth/caddy`
3. Authentik sees the `Authorization: Basic ...` header
4. Authentik validates the service account credentials
5. If valid, Authentik returns a 200 OK to Caddy
6. Caddy forwards the request to Immich
7. Immich handles its own OAuth2 authentication (you still log in with your regular user account)

## Security Considerations

- The base64-encoded credentials are stored in the mobile app (base64 is **not encryption**, just encoding)
- If your phone is compromised, an attacker could extract these credentials
- However, the service account is **limited to Immich only**
- The service account cannot access other homelab services
- You can revoke the service account at any time in Authentik

## Troubleshooting

### Mobile app shows "Unable to connect to server"

1. Verify the base64 string is correct (no extra spaces or line breaks)
2. Check that the service account is active in Authentik
3. Verify the Forward Auth provider is assigned to an outpost

### Mobile app connects but can't log in

1. This is expected - you still need to log in with your regular Immich user
2. The Forward Auth only gets you past the proxy layer
3. After Forward Auth succeeds, use your normal OAuth2 login

### Need to rotate credentials

1. In Authentik, go to the service account
2. Click **Reset Password** and generate a new one
3. Generate a new base64 string with the new password
4. Update the header in the mobile app

---

## Related Configuration

- Caddy configuration: `/Users/florian.veaux/go/src/github.com/FlorianVeaux/homelab/caddy_public/docker-compose.yml`
- Authentik configuration: `/Users/florian.veaux/go/src/github.com/FlorianVeaux/homelab/authentik/docker-compose.yml`
- Forward Auth provider: Configured in Authentik UI under Applications → Providers
