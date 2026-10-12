# Contributing

Thanks for helping. This repository holds the public template format and the SDK that
checks and tests templates. Changes that make the format clearer, the validator stricter
or more helpful, or the runner more faithful are all welcome.

## Before you start

- Bugs: open an issue with the template directory (or a minimal copy), the command you ran
  and its output (`--json` helps).
- Format changes and new features: open an issue first and describe the rule you want
  in the terms of `docs/format.md`. Issues that are not specified enough yet get the
  `needs-spec` label; work starts once the spec is agreed.
- Example templates are welcome when they show a format feature or a shape on a platform
  that no example covers yet. Keep them small, with hand-checked expected tables.

## Making a change

1. Fork, or branch from `main` as `<area>/<topic>` (for example
   `validate/duplicate-tables`); keep branches short-lived.
2. `task setup`, make the change, add tests (see `docs/development.md` for fixtures and
   for adding problem codes).
3. Update `docs/format.md` and `docs/specs/sdk.md` when behavior changes, and add a short
   entry to `log/devlog.md`.
4. `task gate` must pass.
5. Open a pull request into `main`.

Commit messages: `<area>: <what>`, for example `validate: report duplicate table names`;
append `(green)` when `task gate` passed. Branches use the same areas: `format`,
`validate`, `render`, `runner`, `cli`, `scaffold`, `examples`, `fixtures`, `docs`, `ci`.

## Pull requests

- CI runs `task setup` and `task gate`; a red gate blocks the merge.
- Pull requests from branches in this repository also get an automated review against
  `AGENTS.md`. Pull requests from forks skip it because they cannot read repository
  secrets; a maintainer reviews them.
- One topic per pull request. Unrelated formatting or refactoring goes in its own.

## Labels

| Label           | Meaning                                                   |
| --------------- | --------------------------------------------------------- |
| `agent`         | an automated agent implements the issue and opens a PR    |
| `needs-spec`    | not ready to implement until the spec covers it          |
| `bug`           | something is broken                                       |
| `enhancement`   | new capability or improvement                             |
| `documentation` | docs only                                                 |
| `blocked`       | waiting on something outside this repository             |

## License

By contributing you agree that your contribution is licensed under the MIT License of this
repository. The Emolysis name and logo are not covered by that license (see `NOTICE`).
