# Codex Operating Instructions

These instructions apply to this repository. Prefer local project conventions
when they are stricter than the general standards below.

## Operating Model

- Work in small, reversible changes.
- Preserve state before risky upgrades: record branch, status, configs, schemas,
  deployment settings, and rollback notes.
- Use `.hermes/run.lock` for autonomous Hermes/Mythos runs. If a lock exists,
  inspect it and continue only when the prior run is complete or clearly stale.
- Never commit secrets, tokens, private keys, cookies, `.env` files, or
  user-private data.
- Use current official documentation before changing code that depends on a
  library, framework, SDK, API, CLI, cloud service, database, or deployment
  platform. Use Context7 first when available.
- Keep commits small and verified. Use Conventional Commits:
  `type(scope): description`.

## Repository Workflow

Before editing:

1. Check `git status --short --branch`.
2. Create a checkpoint branch before risky or broad changes.
3. Identify the package manager, test commands, app entrypoints, deployment
   config, database config, and runtime services.
4. Run the smallest relevant baseline checks available in the environment.

After editing:

1. Format only files you intentionally touched.
2. Run targeted tests first, then broader tests when practical.
3. Run secret scanning when env, deployment, auth, or config files change.
4. Update docs and memory/index files for user-visible behavior or operating
   contracts.
5. Record blocked checks with the exact missing tool or environment issue.

## General Engineering Standards

- Favor readability, explicit errors, typed interfaces where the language
  supports them, structured logging, and narrow modules.
- Match existing style before introducing new abstractions.
- Add abstractions only when they remove real duplication or clarify a shared
  contract.
- Use parsers, ASTs, schema validators, or framework APIs instead of ad hoc text
  parsing when available.
- Prefer tests that cover behavior and contracts over tests that mirror
  implementation details.
- Document configuration, rollback paths, migration steps, and deployment
  assumptions.

## Language And Platform Standards

Use the standard most applicable to the file being edited:

- Python: follow PEP 8 and PEP 257; use type hints where useful; prefer pytest
  for tests; keep import-time side effects out of tests and static inspectors.
- JavaScript and TypeScript: follow the active project formatter/linter first;
  use strict TypeScript where available; prefer `const`, explicit async error
  handling, and modern ESM or the existing project module convention.
- Discord bots: follow current Discord API and discord.py or discord.js docs;
  handle intents, permissions, reconnects, rate limits, and application-command
  sync explicitly.
- Java: use the project style, otherwise Google Java Style or Oracle
  conventions; use Javadoc for public APIs.
- Go: run `gofmt`; follow Effective Go and Go Code Review Comments.
- Rust: run `rustfmt`; follow Rust API Guidelines for public APIs and error
  types.
- C and C++: follow the existing project formatter; prefer C++ Core Guidelines
  for modern C++; use MISRA or CERT guidance when safety-critical constraints
  are in scope.
- C#: follow Microsoft C# coding conventions; use XML docs for public APIs.
- PHP: follow PSR-12 and PHPDoc where applicable.
- Ruby: follow the community Ruby Style Guide and YARD or RDoc conventions.
- HTML and CSS: follow semantic HTML, maintainable selectors, and WCAG 2.2
  accessibility guidance.
- SQL and databases: use migrations, schema versioning, backups, indexes for
  lookup paths, and tested rollback plans.
- Docker: follow Dockerfile best practices: small trusted bases, reproducible
  builds, `.dockerignore`, non-root users where practical, health checks, and
  CI builds.
- Kubernetes: use declarative manifests, readiness/liveness/startup probes,
  resource requests/limits, clear secret strategy, and rollback notes.

## Source Anchors

Use these primary references when no stricter project guide exists:

- Python PEP 8: https://peps.python.org/pep-0008/
- Python PEP 257: https://peps.python.org/pep-0257/
- Conventional Commits: https://www.conventionalcommits.org/en/v1.0.0/
- Google Style Guides: https://google.github.io/styleguide/
- Microsoft C# conventions:
  https://learn.microsoft.com/en-us/dotnet/csharp/fundamentals/coding-style/coding-conventions
- Effective Go: https://go.dev/doc/effective_go
- Go Code Review Comments: https://go.dev/wiki/CodeReviewComments
- Rust API Guidelines: https://rust-lang.github.io/api-guidelines/
- PHP PSR-12: https://www.php-fig.org/psr/psr-12/
- Kotlin coding conventions: https://kotlinlang.org/docs/coding-conventions.html
- Swift API Design Guidelines:
  https://www.swift.org/documentation/api-design-guidelines/
- WCAG 2.2: https://www.w3.org/TR/wcag/
- Dockerfile best practices:
  https://docs.docker.com/engine/userguide/eng-image/dockerfile_best-practices/
- Kubernetes probes:
  https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/

## Hermes/Mythos/Camelot Notes

- Treat Mythos packets as explicit state. Prime synthesis should consume
  compiled packets, not raw lane chatter.
- Store durable research and upgrade notes in Camelot-style memory entries with
  summary, source links, evidence, related concepts, risks, dependencies, next
  actions, and retrieval tags.
- Grade completed upgrades for impact, risk, complexity, test coverage,
  maintainability, security, memory/retrieval value, deployment readiness,
  documentation quality, and user value.
