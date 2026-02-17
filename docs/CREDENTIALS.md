# 🔐 Credential Reference Map

> **⚠️ This file contains NO actual passwords or secrets.**
> It serves as a reference map for where credentials are used and stored.

---

## Credential References

| Ref Key | Service | Purpose | Storage Location |
|---------|---------|---------|-----------------|
| `godaddyPw` | GoDaddy | WordPress hosting / cPanel access | Owner's password manager |
| `HiveEmail` | HiveMQ | MQTT broker account email | Owner's password manager |
| `HivePw` | HiveMQ | MQTT broker account password | Owner's password manager |

---

## Security Policy

1. **Never commit credentials** to this repository — not even in comments or examples.
2. **Environment variables** or **config files** outside the repo should be used for runtime secrets.
3. **Rotate credentials** if any accidental exposure occurs.
4. **Raspberry Pi access** credentials are managed separately and not tracked here.

---

## Where Credentials Are Used

### GoDaddy (`godaddyPw`)
- WordPress admin panel: `farcomindustrial.com/wp-admin`
- cPanel / hosting management
- Domain DNS settings

### HiveMQ (`HiveEmail`, `HivePw`)
- MQTT broker authentication (when using authenticated mode)
- HiveMQ Cloud console: `console.hivemq.cloud`
- Currently using public broker (`broker.hivemq.com:1883`) — no auth required
- Future: migrate to authenticated HiveMQ Cloud for production security

---

## Future Security Roadmap

- [ ] Migrate from public MQTT broker to authenticated HiveMQ Cloud
- [ ] Implement TLS/SSL for MQTT connections (port 8883)
- [ ] Add `.env` file support for Pi-side credential management
- [ ] Set up GitHub Secrets for CI/CD pipelines
- [ ] Enable 2FA on all service accounts

---

*© 2024–2026 Ing. Aaron Farias — Farcom Industrial. All Rights Reserved.*
