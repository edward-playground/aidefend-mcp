# Security Policy

## Overview

The AIDEFEND MCP Service is built with security-first principles. All processing happens locally with comprehensive input validation and protection against common vulnerabilities.

## Security Features

- ✅ **Local-Only Processing** - Queries never leave your infrastructure
- ✅ **Input Validation** - Protection against injection attacks (XSS, command injection, path traversal)
- ✅ **Rate Limiting** - DoS protection with configurable limits
- ✅ **Security Headers** - HSTS, CSP, X-Frame-Options, etc.
- ✅ **Docker Hardening** - Non-root user, minimal privileges
- ✅ **Secure Logging** - Automatic filtering of sensitive data

## Reporting Security Issues

**Please DO NOT report security vulnerabilities via public GitHub issues.**

To report security vulnerabilities, please contact [Edward Lee on LinkedIn](https://www.linkedin.com/in/go-edwardlee/).

## Production Deployment Tips

1. **Use HTTPS** - Deploy behind reverse proxy (nginx, Caddy, Traefik)
2. **Network Isolation** - Use firewall rules to restrict access
3. **Update Dependencies** - Regularly check for security updates
4. **Monitor Logs** - Watch for unusual access patterns

## Pre-Deployment Checklist

- [ ] HTTPS configured with valid certificates
- [ ] Rate limiting enabled
- [ ] Firewall rules in place
- [ ] Log monitoring set up
- [ ] Dependencies scanned for vulnerabilities

## Recognition

Security researchers who responsibly disclose vulnerabilities will be:
- Publicly acknowledged (with permission)
- Credited in release notes

---

**Maintainer**: [Edward Lee](https://github.com/edward-playground)
**Last Updated**: 2025-11-09

For questions, [open an issue](https://github.com/edward-playground/aidefend-mcp/issues).
