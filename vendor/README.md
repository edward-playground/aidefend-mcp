# Vendored Acorn runtime

This directory contains the Acorn 8.15.0 ECMAScript parser runtime used by
`parse_js_module.mjs`. It is copied from the package pinned in
`package-lock.json` and is distributed under Acorn's MIT license in
`ACORN-LICENSE`.

The vendored runtime makes source archives and Python wheels self-contained;
Node.js 18 or newer is still required to execute the static parser.
