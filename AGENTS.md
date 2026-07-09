# projects

## Cursor Cloud specific instructions

This repository is currently an empty starter. The only tracked file on `main` is
`README.md` (contents: `# projects`). There is **no** application code, dependency
manifest (e.g. `package.json`, `requirements.txt`, `pyproject.toml`, `go.mod`),
test suite, or build system yet.

Practical implications for future agents:

- There is nothing to install, lint, test, build, or run until source code and a
  dependency manifest are added. Do not fabricate a build/run flow that does not
  exist.
- The VM already provides common language runtimes (verified: Python 3.12,
  Node.js 22, Go 1.22, Rust 1.83, Java 21, `pip`, `npm`, `pnpm`, `yarn`). Use them
  directly for quick scripts.
- When real code is added, put its actual setup/lint/test/build/run commands in
  this section and wire dependency installation into the startup update script.
  The current update script is intentionally a guarded no-op that installs from a
  manifest only if one is present, so it stays safe while the repo is empty.
