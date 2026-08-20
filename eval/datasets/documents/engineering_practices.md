# Engineering Practices

## Code Review Guidelines

Every pull request requires at least one approval from a code owner before
merging; pull requests touching authentication, billing, or data-deletion
code paths require two approvals, at least one from a senior engineer.
Reviewers are expected to respond with either an approval, requested
changes, or a comment within one business day of being requested — if a
reviewer cannot meet that window, they should reassign the review rather
than let it sit unanswered.

Pull requests should be kept under 400 changed lines where practical; larger
changes should be split into a stacked series of smaller, independently
reviewable pull requests. Every pull request must include a test for the
behavior it changes, unless the change is a pure refactor with no behavior
change, in which case the existing test suite passing is sufficient.

## Deployment Process

Deployments to production happen automatically on merge to the main branch,
gated by the full CI suite (lint, type-check, unit tests, and integration
tests) passing. A deployment is considered complete once the new version's
health check endpoint returns healthy for 5 consecutive minutes; if it does
not, the deployment pipeline automatically rolls back to the previous
version without requiring manual intervention.

Deployments are paused automatically between 4:00 PM Friday and 8:00 AM
Monday (in the primary engineering time zone) to avoid shipping changes
without adequate follow-up coverage over the weekend — emergency hotfixes
for active incidents are the only exception, and require sign-off from the
on-call engineering lead.

## On-Call Rotation

Engineers rotate through a one-week on-call shift, handed off every Monday
at 10:00 AM. The on-call engineer carries the pager for production incidents
and is expected to acknowledge a page within 15 minutes during business
hours and within 30 minutes outside business hours. Each on-call week is
compensated with an additional day of PTO, credited the following month.

New engineers join the on-call rotation only after completing a shadow
rotation (observing, without carrying the pager) and passing an incident-
response training session with their team lead.

## Incident Response

Incidents are classified into three severities. A Severity 1 incident
(complete outage or data loss affecting all customers) requires the on-call
engineer to open an incident channel and page the engineering lead within 5
minutes of detection. A Severity 2 incident (significant feature degradation
affecting a subset of customers) requires an incident channel within 15
minutes. A Severity 3 incident (minor, non-customer-facing issue) can be
handled through the normal ticket queue without a dedicated incident
channel.

Every Severity 1 and Severity 2 incident requires a written postmortem
within 5 business days of resolution, covering the timeline, root cause,
customer impact, and concrete follow-up action items with owners and due
dates. Postmortems are blameless by policy — the goal is identifying process
and system gaps, not individual fault.
