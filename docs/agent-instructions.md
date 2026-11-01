# Agent Instructions

I layer context files:

- **Core**: How I work and how agents should work with me, for every harness
- **Harness**: Harness specific context
- **Workspace**: Workspace specific info
- **Repository**: Repository specific info

## Core

This is common, general information about me, my values, how I work, and how agents should work with me.

It is `.includes/CORE-INSTRUCTIONS.md`, which chezmoi includes at the top of each harness file.

## Harness

These files provide harness/provider specific instructions. This helps shape agent specific behavior.

- `~/.claude/CLAUDE.md`: Claude Code
- `~/.codex/AGENTS.md`: Codex
- `~/.pi/agent/AGENTS.md`: pi

Grok (`~/.grok/AGENTS.md`) is deferred until I have access.

## Workspace

These instructions provide high level context about the specific workspace the agent is working in.

This file is `workspace/AGENTS.md` in the host workspace folder, rendered by the workspace template and mounted at `/workspace/AGENTS.md`.

## Repository

Each repo may have an AGENTS.md at the root or in any subfolder of the repo. These files of course provide repository specific information.

They generally contain the following sections:

- An elevator pitch for the repository.
- Why it exists. What problems or opportunities does it solve or provide?
- Priorities and Invariants. Things that must hold true about the experience/implementation.
- Glossary. Common terms we use when speaking about the repository.
- Thar be dragons. Common _agentic_ failures _specific to this repository_.

Everything else the agent can discover in standard places in the repo.