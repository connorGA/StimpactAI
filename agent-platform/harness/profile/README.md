# Harness Repository Profile

The harness can load a repo-local profile from `.stimpactai/profile.yml`.

This profile tells the runtime how to install, build, test, start, and browser-verify a repository before agent sessions begin.

## Supported Fields

- `install_command`
- `build_command`
- `test_command`
- `start_command`
- `browser_verification_entrypoints`
- `environment_assumptions`
- `ignored_directories`
- `language_hints`

## Example

See `example_profile.yml` in this directory for a complete sample.
