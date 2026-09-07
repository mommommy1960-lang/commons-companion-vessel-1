# Commons Governance Invariants

These invariants apply to every release, contributor, automation, agent, and subsystem in this repository.

1. Trust never grants authority.
2. Consent is scoped, revocable, and time-bounded where appropriate.
3. Default deny applies to consequential actions.
4. No system may silently expand its own capability scope.
5. No system may disable, rewrite, or bypass its governing policy.
6. Every consequential action must be attributable and auditable.
7. External actuation must remain independently interruptible.
8. Safety controls must survive maintainer succession.
9. Simulation, prototype, verified implementation, and speculation must be labeled separately.
10. Emergency framing does not automatically override rights, consent, or governance.
11. High-risk capability changes require independent review.
12. No system is the sole authority on its own moral status, safety status, or permission scope.

## Decision rule

A Commons technology is not ready merely because it works. It is ready only when its misuse pathways are bounded, observable, interruptible, auditable, and recoverable.

## Enforcement

Consequential changes must state capability impact, evidence, tests, rollback, and approvers. Exceptions require written scope, named approval, a time limit, rollback instructions, and an audit record.
