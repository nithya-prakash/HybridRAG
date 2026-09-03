# Incident Response Runbook

## Severity Levels

Incidents are classified into four severity levels. Severity 1 (Sev1): the
product is completely unavailable for all customers, or customer data has
been exposed — requires immediate all-hands response. Severity 2 (Sev2): a
major feature is broken or severely degraded for a significant subset of
customers. Severity 3 (Sev3): a minor feature is broken or degraded, with a
reasonable workaround available. Severity 4 (Sev4): a cosmetic issue or a
problem affecting a single customer with no broader impact.

## Roles During an Incident

Every Sev1 or Sev2 incident is assigned an Incident Commander (IC), who owns
the response and has final say on remediation steps, and a Communications
Lead, who is solely responsible for posting status page updates and
customer-facing communication so that responders aren't distracted by
external messaging. The first engineer to acknowledge a page becomes the IC
by default until they explicitly hand off the role to someone else in the
incident channel.

## Response Time Targets

The Incident Commander must be assigned within 10 minutes of a Sev1 being
declared, and within 20 minutes for a Sev2. The Communications Lead must
post an initial status page update within 15 minutes of a Sev1 being
declared. Sev3 incidents do not require a dedicated status page update
unless the workaround is non-obvious.

## Status Page Communication

Status page updates during a Sev1 must be posted at least every 30 minutes
until resolution, even if the update is only "still investigating." The
final resolution update must include a one-sentence, non-technical summary
of what happened and confirmation that the issue is fully resolved — root
cause detail belongs in the postmortem, not the status page.

## Rollback Procedure

Any deployment suspected of causing a Sev1 or Sev2 must be rolled back
immediately, before root-causing the issue, unless the IC determines that
rolling back would make the situation worse. A rollback is considered
complete only once the previous version's health checks have been green for
5 consecutive minutes, matching the same health-check-stability requirement
used for forward deployments.

## Postmortem Requirements

Every Sev1 incident requires a written postmortem within 3 business days of
resolution, reviewed by the engineering director before being shared
company-wide. Sev2 incidents require a postmortem within 5 business days,
reviewed by the responsible team's lead. The postmortem must include a
timeline, root cause, customer impact in concrete terms (e.g. number of
affected requests or accounts), and at least one concrete follow-up action
with an assigned owner and due date — a postmortem with no action items is
sent back for revision.

## On-Call Escalation

If the primary on-call engineer does not acknowledge a page within 10
minutes, the page automatically escalates to the secondary on-call engineer.
If neither acknowledges within 20 minutes total, the page escalates to the
engineering director directly. An on-call rotation shift is one full week,
handed off every Monday at 10:00 AM in the team's primary time zone, and no
engineer may be scheduled for two consecutive on-call weeks without an
explicit exception approved by their manager.

## Chaos Testing

Each service team runs a chaos testing exercise (a deliberately injected
failure, such as killing a database connection pool or introducing network
latency) at least once per quarter, coordinated in advance with the
Infrastructure team and never run during a company-wide feature freeze.
