# CLI and UX

## Proposed commands

```text
si inspect <target>
si diagnose <target>
si research <target>
si design <target>
si improve <target>
si propose <target>
si verify <target>
si report <target>
si diff <snapshot-a> <snapshot-b>
si watch <target>
si doctor
```

## Natural language

The agent layer should map intents to commands/capabilities.

Examples:
- "このリポジトリを診断して"
- "このSkillは本当に使われている？"
- "この構成に足りないものは？"
- "もっと良い実装がGitHubにないか調べて"
- "なければ作るべきか判断して"
- "改善案をDraft PRにして"

## Output format

Always lead with:
1. Executive summary
2. Verified facts
3. Findings
4. Recommendations
5. Proposed actions
6. Required approvals
7. Evidence

Avoid burying critical findings in prose.
