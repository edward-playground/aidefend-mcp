# Third-Party Content and Runtime Components

## AIDEFEND AI Defense Framework

This service downloads, transforms, indexes, and returns content from the
AIDEFEND AI Defense Framework.

> AIDEFEND AI Defense Framework, created by Edward Lee,
> https://aidefend.net, licensed under CC BY 4.0.

Framework content and data are licensed under the Creative Commons
Attribution 4.0 International license. Framework software is licensed under
Apache License 2.0. Those licenses do not grant trademark rights or imply
endorsement. See the framework repository's `LICENSING.md`,
`LICENSE-CONTENT`, `NOTICE`, and `TRADEMARKS.md` for the authoritative terms.

The synchronized `data/framework-migrations.json` registry includes normalized
OWASP Top 10 for LLM Applications identifiers, risk names, edition metadata,
and paraphrased summaries under CC BY-SA 4.0. Its embedded `sourceLicense`
metadata provides attribution, license URL, scope, and changes made. AIDEFEND's
mapping decisions and resolver behavior are independently authored. Downstream
users should preserve the registry's source-license metadata when redistributing
that material.

## Acorn

The Python distribution includes Acorn 8.18.0's `dist/acorn.mjs` JavaScript
parser runtime, copied verbatim from the official npm package, for static
parsing of framework source files. The package is lock-pinned with its npm
registry integrity value. Acorn is licensed under the MIT License; its license
is distributed with the packaged runtime.
