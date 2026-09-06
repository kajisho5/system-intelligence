# Target Architecture

```text
                    User / Agent Harness
                           |
                    Command / Intent
                           |
                 +---------v----------+
                 | Orchestration Core |
                 +---------+----------+
                           |
        +------------------+------------------+
        |                  |                  |
        v                  v                  v
   Discovery          Analysis            Research
        |                  |                  |
        +------------------+------------------+
                           |
                    Intelligence Model
                           |
        +------------------+------------------+
        |                  |                  |
        v                  v                  v
     Audit            Recommendation      Design
        |                  |                  |
        +------------------+------------------+
                           |
                  Approval / Policy Gate
                           |
                +----------+----------+
                |                     |
                v                     v
             Proposal              Execute
                                      |
                                      v
                                  Verify
                                      |
                                      v
                              State + Reports
                                      |
                          +-----------+----------+
                          |                      |
                          v                      v
                       HTML                  Dashboard API
```

## Architectural layers

1. Interface layer
2. Intent router
3. Orchestration layer
4. Discovery adapters
5. Static/deterministic analyzers
6. Semantic analyzers
7. External research adapters
8. Domain model / graph
9. Policy engine
10. Recommendation engine
11. Change planner
12. Execution adapters
13. Verification engine
14. State store
15. Report/dashboard exporter

## Core rule

The LLM should not be the only source of truth.

Deterministic facts should be produced by scanners/parsers whenever possible. The model interprets evidence and generates hypotheses/recommendations.
