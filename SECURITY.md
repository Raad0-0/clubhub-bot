# Security Policy

## Reporting Security Issues
We take the security and privacy of community servers seriously. If you discover a security vulnerability or privacy leak (such as an authorization bypass, unintended channel visibility, or token exposure), please report it responsibly.

### How to Report
Please **DO NOT** report security vulnerabilities via public GitHub issues or discussions.

Instead, please send an encrypted email or private disclosure message to the project maintainers with:
1. A description of the issue and its potential impact.
2. Step-by-step instructions or proof-of-concept to reproduce the vulnerability.
3. Relevant configuration files (with tokens and private data redacted).

We will acknowledge receipt within 48 hours and work on a fix promptly.

## Supported Versions
Only the latest release on the `main` branch receives active security updates.

| Version | Supported |
|:---|:---|
| 0.1.x | Yes |
| < 0.1.0 | No |

## Best Practices for Deployment
- Never commit `.env` or `credentials.json` files to source control.
- Ensure the bot runs with minimal necessary permissions (manage channels, manage roles, send messages, read messages, connect, speak).
- Note that Discord Server Administrators technically have administrative access to all Discord channels by design; the bot enforces role-based separation between Member, Support, and Private Concern teams, but cannot hide channels from users with the native Discord `Administrator` permission.
