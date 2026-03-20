"""
API Key Generator for AIDEFEND MCP Service

Generates a cryptographically secure random API key for use with AUTH_MODE=api_key.
The generated key can be used in the .env file as AIDEFEND_API_KEY.

Usage:
    python scripts/generate_api_key.py

Output:
    A 32-byte URL-safe base64-encoded random string (approximately 43 characters)

Security Notes:
    - Uses secrets.token_urlsafe() for cryptographically strong randomness
    - Suitable for production use
    - Keep the generated key private and secure
    - Do not commit API keys to version control
"""

import secrets
import sys


def generate_api_key(length: int = 32) -> str:
    """
    Generate a cryptographically secure random API key.

    Args:
        length: Number of bytes of randomness (default: 32 bytes = 256 bits)

    Returns:
        URL-safe base64-encoded random string

    Security:
        Uses secrets.token_urlsafe() which is suitable for security tokens.
        32 bytes provides 256 bits of entropy, which is highly secure.
    """
    return secrets.token_urlsafe(length)


def main():
    """Main entry point for API key generation."""
    print("=" * 70)
    print("AIDEFEND MCP Service - API Key Generator")
    print("=" * 70)
    print()

    # Generate API key
    api_key = generate_api_key()

    print("Generated API Key (keep this secret!):")
    print()
    print(f"  {api_key}")
    print()
    print("=" * 70)
    print("Configuration Instructions:")
    print("=" * 70)
    print()
    print("1. Add the following lines to your .env file:")
    print()
    print("   # Authentication Configuration")
    print("   AUTH_MODE=api_key")
    print(f"   AIDEFEND_API_KEY={api_key}")
    print()
    print("2. Restart the AIDEFEND service:")
    print()
    print("   python __main__.py")
    print()
    print("3. When making API requests, include the API key in the header:")
    print()
    print("   X-API-Key: " + api_key)
    print()
    print("   Example using curl:")
    print()
    print("   curl -H 'X-API-Key: " + api_key + "' \\")
    print("        http://localhost:8000/api/v1/status")
    print()
    print("   Example using Python requests:")
    print()
    print("   import requests")
    print("   headers = {'X-API-Key': '" + api_key + "'}")
    print("   response = requests.post(")
    print("       'http://localhost:8000/api/v1/query',")
    print("       headers=headers,")
    print("       json={'query_text': 'prompt injection', 'top_k': 5}")
    print("   )")
    print()
    print("=" * 70)
    print("Security Reminders:")
    print("=" * 70)
    print()
    print("  - Keep this API key private and secure")
    print("  - Do NOT commit .env files to version control")
    print("  - Rotate the key periodically for enhanced security")
    print("  - Use different keys for different environments (dev/staging/prod)")
    print("  - If the key is compromised, generate a new one immediately")
    print()
    print("For more information, see SECURITY.md")
    print("=" * 70)
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nAPI key generation cancelled by user", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"\nError generating API key: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
