# SDK repository sync checklist

- [x] Inspect the original flopkit SDK source and exclude generated caches, coverage files, and local artifacts.
- [x] Copy the SDK source, tests, packaging, documentation, CI, and license files into the GitHub repository without overwriting the website.
- [x] Run the SDK test, coverage, lint, type-check, and documentation checks from the combined repository.
- [x] Scan tracked files and Git history for private keys, credentials, or other secret values.
- [ ] Commit and push the combined project to the GitHub repository.
- [ ] Verify the remote repository contains both the website and the SDK.
