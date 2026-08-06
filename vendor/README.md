# Vendored Acorn runtime

This directory contains the Acorn 8.18.0 ECMAScript parser runtime used by
`parse_js_module.mjs`. `acorn.mjs` is copied verbatim from `dist/acorn.mjs` in
the official `acorn-8.18.0.tgz` npm package and is distributed under Acorn's
MIT license in `ACORN-LICENSE`.

Audit metadata:

- npm package integrity: `sha512-lGq+9yr1/GuAWaVYIHRjvvySG5/4VfKIvC8EWxStPdcDh/Ka7FG3twP6v4d5BkravUilhIAsG4Qj83t02LWUPQ==`
- `vendor/acorn.mjs` SHA-256: `953573b8fdab71599749ea5f2b33d3e760c2116178f9423ee7458dbe39d59453`
- exact dependency pin: `package.json` and `package-lock.json`

The vendored runtime makes source archives and Python wheels self-contained;
Node.js 18 or newer is still required to execute the static parser.
