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
- ✅ **Flexible Authentication** - API key auth for production, optional for local dev

## Local Data-Path Isolation

The local LanceDB deployment treats each configured `DATA_PATH` as an exclusive
single-process boundary. One REST server, stdio MCP server, `--resync` command,
or maintenance process may own that directory at a time. This protects the
database table, raw source snapshot, and version metadata from cross-process
replacement while another process retains live database handles.

- Do not run REST and MCP concurrently against the same `DATA_PATH`.
- If both modes are required, use independent `DATA_PATH` values and keep each
  instance's `DB_PATH`, `RAW_PATH`, and `VERSION_FILE` private to that instance.
- Do not mount one writable data volume into multiple service replicas.
- For horizontal scaling, use independent data copies or an external data layer
  designed for concurrent clients; do not share the bundled LanceDB files.

`DATA_PATH/sync.lock` is a persistent rendezvous file. File presence and file
age are not proof that a live lock exists; the operating-system lock is the
authority. Never delete or replace `sync.lock` to force startup or resync.
Stop the current owner or select a different complete storage-path set.

Before upgrading from a release that did not hold the data-path lock throughout
the service lifetime, stop all REST processes, close MCP clients that launch
the stdio server, and allow every maintenance operation to finish. Older
processes cannot be assumed to honor the new ownership contract.

## Authentication & Authorization

### Dual-Mode Security Model

AIDEFEND MCP Service operates in two modes with different security models:

#### 1. **MCP Mode** (Claude Desktop Integration)
- **Transport**: stdio (standard input/output)
- **Authentication**: Secured via **file system permissions**
- **Threat Model**: Local execution, no network exposure
- **Best Practices**:
  - Restrict execution permissions on `__main__.py` and `mcp_server.py`
  - Protect Claude Desktop config file (`chmod 600 ~/Library/Application\ Support/Claude/claude_desktop_config.json`)
  - Limit access to `data/` directory containing knowledge base

#### 2. **REST API Mode** (HTTP Integration)
- **Transport**: HTTP/HTTPS
- **Authentication**: Configurable via `AUTH_MODE`
- **Two modes available**:

##### `AUTH_MODE=no_auth` (Default)
- **Purpose**: Local development, personal use
- **Security**: NO authentication required
- **Suitable for**:
  - ✅ Local development on `localhost`, `127.0.0.0/8`, or `::1`
  - ✅ Personal use on your own machine
- **NOT suitable for**:
  - ❌ Production deployment
  - ❌ Public networks
  - ❌ Private/LAN network bindings
  - ❌ Team collaboration over network
- **Enforced Safety**: With `no_auth`, the service starts only for an explicit
  loopback IP or `localhost`; wildcard, LAN/public IP, empty, and unknown
  hostname bindings are rejected

##### `AUTH_MODE=api_key` (Production)
- **Purpose**: Production deployment, team collaboration
- **Security**: Requires API key in `X-API-Key` header
- **Implementation**:
  ```bash
  # 1. Generate secure API key
  python scripts/generate_api_key.py

  # 2. Configure in .env
  AUTH_MODE=api_key
  AIDEFEND_API_KEY=<your-generated-key>

  # 3. Include key in requests
  curl -H "X-API-Key: <your-key>" http://localhost:8000/api/v1/query
  ```
- **Security Features**:
  - Cryptographically secure key generation (`secrets.token_urlsafe`)
  - Constant-time comparison to prevent timing attacks (`secrets.compare_digest`)
  - Failed authentication attempts logged for monitoring
  - Rate limiting applies regardless of auth mode

### API Key Management Best Practices

1. **Generation**:
   - Always use `scripts/generate_api_key.py` for cryptographically secure keys
   - Never use weak or predictable keys

2. **Storage**:
   - Store keys in `.env` file (never in source code)
   - Add `.env` to `.gitignore` (already configured)
   - Use different keys for different environments (dev/staging/prod)

3. **Rotation**:
   - Rotate keys periodically (every 90 days recommended)
   - Immediately rotate if compromise suspected
   - Generate new key with `python scripts/generate_api_key.py`

4. **Distribution**:
   - Share keys securely (e.g., password manager, encrypted channel)
   - Never commit keys to version control
   - Never share keys in plain text emails or chat

5. **Monitoring**:
   - Monitor logs for failed authentication attempts
   - Set up alerts for unusual access patterns
   - Review `data/logs/aidefend_mcp.log` regularly

### Public Endpoints (No Authentication)

The following endpoints are **always public** (no authentication required):

- `GET /health` - Health check for monitoring tools (Kubernetes probes, load balancers)
- `GET /` - Service information and documentation links

All other endpoints require authentication when `AUTH_MODE=api_key`.

## Reporting Security Issues

**Please DO NOT report security vulnerabilities via public GitHub issues.**

To report security vulnerabilities, please contact [Edward Lee on LinkedIn](https://www.linkedin.com/in/go-edwardlee/).

## Production Deployment Tips

1. **Use HTTPS** - Deploy behind reverse proxy (nginx, Caddy, Traefik)
2. **Network Isolation** - Use firewall rules to restrict access
3. **Update Dependencies** - Regularly check for security updates
4. **Monitor Logs** - Watch for unusual access patterns

## Pre-Deployment Checklist

### Authentication & Access Control
- [ ] `AUTH_MODE=api_key` configured in .env
- [ ] Strong API key generated using `scripts/generate_api_key.py`
- [ ] `.env` file excluded from version control (check `.gitignore`)
- [ ] API key securely distributed to authorized users only
- [ ] Different keys used for dev/staging/prod environments

### Network Security
- [ ] HTTPS configured with valid certificates (reverse proxy)
- [ ] `API_HOST=127.0.0.1` or proper firewall rules if binding to `0.0.0.0`
- [ ] Firewall rules restrict access to authorized IPs only
- [ ] CORS origins configured for specific domains (not `*`)

### Monitoring & Operations
- [ ] Rate limiting enabled (`ENABLE_RATE_LIMITING=true`)
- [ ] Log monitoring set up for authentication failures
- [ ] Alerts configured for unusual access patterns
- [ ] Regular log review scheduled (`data/logs/aidefend_mcp.log`)
- [ ] Exactly one REST, MCP, resync, or maintenance process uses each `DATA_PATH`
- [ ] Every replica has independent storage; no writable LanceDB volume is shared
- [ ] Operational procedures never delete `sync.lock` to bypass ownership

### Dependencies & Updates
- [ ] Dependencies scanned for vulnerabilities (`pip list --outdated`, `safety check`)
- [ ] Regular update schedule established
- [ ] Security patch procedure documented

## Recognition

Security researchers who responsibly disclose vulnerabilities will be:
- Publicly acknowledged (with permission)
- Credited in release notes

---

**Maintainer**: [Edward Lee](https://github.com/edward-playground)
**Last Updated**: 2026-08-04

For questions, [open an issue](https://github.com/edward-playground/aidefend-mcp/issues).
