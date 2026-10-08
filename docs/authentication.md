# Authentication

## Standalone

Django provides Argon2id password hashing, server-side sessions, CSRF protection and password validation. The interactive `account` command bootstraps the first owner and provides administrator-controlled recovery. Owners may enrol members through the UI. There is no email requirement, public signup, default account, password in CLI arguments or automatically sent invitation. Local login has a per-username attempt limit; also apply a proxy-wide rate limit on internet-facing installations.

## Authentik

Reuse your existing Authentik. Create two non-superuser, app-specific groups, `stash-owners` and `stash-members`, and assign existing users. Bind only those groups to the Stash application with an any-match policy. Membership in the owner group grants Stash administration, not Authentik administration.

Create a confidential OAuth2/OIDC provider:

- Grant: authorization code only; use an existing authentication and consent flow.
- Exact redirect URI: `https://stash.example.com/auth/callback` (strict match).
- Per-provider issuer, user UUID subject mode and asymmetric signing key.
- Scopes `openid profile email groups`; include the group names in the ID token.
- Use the issuer returned by discovery, commonly `https://auth.example.com/application/o/stash/`, not the service root.

Set `AUTH_MODE`, `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_OWNER_GROUP`, `OIDC_MEMBER_GROUP` and `ORIGIN` in a protected environment file. Recreate the app. Keep secrets out of frontend bundles and source control. Configure the reverse proxy to send HTTPS scheme and the canonical Host; the backend must only accept the trusted proxy.

Authlib performs code exchange, S256 PKCE, state/nonce and signed ID-token validation. The exact issuer is required. Stash rejects identities outside the two configured groups and binds users only by issuer + subject. An existing local account with a matching email/name is not linked. OIDC mode has no local sign-in route or break-glass account. Recover the identity service or use host administration to restore the installation.

The same household database serves all permitted members. Each user's selected tub, drafts and installation handoff are separate. Secure, HttpOnly, host-only, SameSite=Lax cookies hold opaque Django session IDs. Sessions last one hour. OIDC group changes take effect on the next login; existing sessions can last until expiry. Stash logout ends the Stash session; the identity provider's SSO session may remain, allowing immediate sign-in. End the IdP session separately on shared devices.

API credentials are explicitly issued by owners, expire in 30 days, and can be revoked. They are separate from IdP group revocation: revoke these credentials when removing access, or disable the corresponding Stash user through trusted administration. Pairings only select containers; they cannot read inventory or move stock.

Never treat account provisioning or administrator impersonation tests as proof that a person has signed in on their own device.
