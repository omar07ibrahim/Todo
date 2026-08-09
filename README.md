# Todo security baseline

This repository preserves Omar's 2023 task-list prototype while its next portfolio-grade iteration is built. The current tip is a remediation baseline, not yet the final product.

## Security-first setup

The application no longer contains runtime credentials. Before importing or starting it, provide a private Flask signing secret with at least 32 non-whitespace characters:

```bash
export TODO_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
```

Weather is optional and disabled unless `OPENWEATHER_API_KEY` is supplied through the environment. The key is sent only as an HTTPS query parameter to the configured provider; it is never printed. Network calls have bounded connect/read timeouts and return a generic failure message.

The legacy task mutations now require `POST`, submitted values are stripped and bounded to 200 characters, debug mode is disabled, and session cookies are HTTP-only with `SameSite=Lax`. Set `TODO_COOKIE_SECURE=1` behind HTTPS.

## Historical credential notice

Removing a credential from the current tree does not erase it from Git history. Any credential ever committed to this public repository must be treated as exposed and revoked at its provider. Do not reuse historical values.

## Current boundary

This is an interim containment release. It retains the legacy Flask/SQLAlchemy UI and remote Bootstrap/jQuery assets. Dependency locking, CSRF protection, deterministic planning, full tests, offline assets, and reproducible visual evidence belong to the next reviewed iteration and are not claimed here.
