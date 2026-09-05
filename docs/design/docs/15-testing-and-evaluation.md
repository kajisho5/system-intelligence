# Testing and Evaluation

## Test layers

### Unit
- parsers
- detectors
- graph operations
- scoring
- policy engine

### Integration
- local repositories
- GitHub fixtures
- external research adapters
- report generation

### End-to-end
Curated target projects:
1. ordinary Python application
2. ordinary TypeScript application
3. Agent project
4. Agent Skills project
5. multi-repository ecosystem
6. intentionally unhealthy project
7. AI Video Production OS reference environment

## Golden datasets

Maintain expected findings for fixture repositories.

## Evaluation dimensions

- discovery recall
- finding precision
- false-positive rate
- recommendation usefulness
- evidence coverage
- reproducibility
- safety policy adherence

## Regression rule

A new analyzer must not silently change previously verified findings without a versioned reason.
