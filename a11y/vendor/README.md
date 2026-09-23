# Vendored axe-core

`axe.min.js` is axe-core 4.13.0, exactly as published on npm.

- Source: https://registry.npmjs.org/axe-core/-/axe-core-4.13.0.tgz, file `package/axe.min.js`
- SHA-256 of `axe.min.js`: `c24f097bd2f451d4f933e8bc7d8d539f8672a2ebcb5cc9f9f3eec8ca9470a0c1`
  (the package's own `sri-history.json` lists the same digest for this file, as
  `sha256-wk8Je9L0UdT5M+i8fY1Tn4ZyouvLXMn58+7IypRwoME=`)
- Licence: Mozilla Public License 2.0, in `axe-core-LICENSE.txt` (the package's `LICENSE`, unchanged)

The scan (`a11y/axe.py`) puts this file into every page it checks, so the
version that runs is the one named here, whatever is installed elsewhere, and
no test needs the network. `tests/test_vendor.py` checks the file against the
checksum above and its banner against the version, so a changed file fails the
suite. To move to another version: replace the file and the licence, then write
the new version and checksum here.
