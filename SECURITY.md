# Security policy

Please report vulnerabilities through GitHub private vulnerability reporting rather than a public issue.

## Credential handling

- Runtime secrets belong only in environment variables or ignored local files.
- Never commit `.env`, database files, access tokens, API keys, or real task data.
- Treat every credential that has appeared in public Git history as compromised and revoke it at the issuing provider.
- A deletion commit does not purge historical Git objects.

The optional weather integration is disabled without `OPENWEATHER_API_KEY`. The required Flask signing value is read from `TODO_SECRET_KEY` and must contain at least 32 non-whitespace characters.

## Supported state

Only the latest protected default branch is supported. This legacy containment baseline is not yet recommended for internet deployment; its documented current boundary remains part of the security contract.
