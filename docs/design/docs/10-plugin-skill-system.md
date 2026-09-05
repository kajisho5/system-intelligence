# Plugin and Skill System

## Principle

One repository, modular capabilities.

Core functionality lives in System Intelligence. Optional analyzers can be internal modules or external Skills/plugins.

## Capability discovery

A plugin may declare:
- name
- version
- supported targets
- inputs
- outputs
- permissions
- dependencies
- verification method

## Agent Skills integration

Recognize standard `SKILL.md` layouts and allow System Intelligence to audit them.

Do not require every plugin to be an Agent Skill.

## Provider abstraction

The orchestration layer must not hard-code Claude Code, Codex, Cursor, or a single LLM.

Adapters may expose:
- skill loading
- model invocation
- tool invocation
- file access
- GitHub access
- browser/research access

## Dynamic selection

Given an intent, select the minimum capability set required.

Example:
`diagnose repository` may select:
- repository discovery
- architecture analysis
- documentation audit
- dependency analysis
- CI analysis

It should not blindly activate every installed capability.
