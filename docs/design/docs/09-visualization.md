# Visualization and Dashboard

## Outputs

Generate a static HTML report that can be opened locally or published with GitHub Pages.

### Pages

- Overview
- Architecture
- Components
- Agents
- Skills
- Capabilities
- Dependencies
- Findings
- Recommendations
- Research
- Proposed Changes
- Verification
- History

## Core visualizations

- component graph
- capability graph
- dependency graph
- lifecycle/activity view
- health summary
- finding severity
- recommendation priority
- before/after comparison

## Data contract

Dashboard should consume the canonical snapshot/report schema.

The analyzer must not create a second incompatible source of truth merely for UI.

## Reference implementation integration

AI Video Production OS's dashboard should be able to consume System Intelligence outputs through a documented adapter/export format.
