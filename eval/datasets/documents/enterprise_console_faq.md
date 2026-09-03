# Enterprise Admin Console FAQ

## Single Sign-On

How do I set up SSO? Enterprise plan administrators can configure SAML 2.0
or OIDC single sign-on from the Admin Console under Security Settings.
Once SSO is enabled and enforced, password-based login is disabled for all
members of the workspace except a single designated emergency-access
account, which is exempt from SSO enforcement specifically so admins are
never locked out if the identity provider is unreachable.

Does SSO support just-in-time provisioning? Yes. When just-in-time
provisioning is enabled, a user's first successful SSO login automatically
creates their account with the role specified in the SAML assertion's
group-mapping configuration; without it, an admin must manually invite each
user before they can sign in via SSO.

## Role-Based Access Control

What roles are available? The Admin Console supports four roles: Owner,
Admin, Member, and Viewer. Only Owners can delete the workspace or transfer
billing ownership. Admins can manage members, integrations, and security
settings but cannot delete the workspace. A workspace may have multiple
Owners, but at least one must remain at all times — the console blocks
removing the last remaining Owner.

Can roles be customized? Enterprise plans additionally support custom
roles with granular permissions (e.g., "can view audit logs but not export
them"); custom roles are not available on the Professional or Starter
plans.

## Audit Logs

How long are audit logs retained? Audit logs are retained for 180 days on
the Enterprise plan and 30 days on the Professional plan; the Starter plan
does not include audit log access. Logs can be exported as CSV or streamed
continuously to an external SIEM via webhook, available only on Enterprise.

## Data Residency

Can I choose where my data is stored? Enterprise customers may select a
data residency region (US, EU, or APAC) at signup; changing regions after
signup requires a full data migration performed by the vendor's
infrastructure team and currently takes 2 to 4 weeks depending on account
size.

## IP Allowlisting and Session Controls

Can I restrict login by IP address? Enterprise admins can configure an IP
allowlist; login attempts from outside the allowlisted ranges are rejected
before password or SSO verification is attempted. Session timeout is
configurable between 15 minutes and 24 hours; the platform default for
newly created Enterprise workspaces is 8 hours.

## Uptime SLA

What uptime does the Enterprise plan guarantee? The Enterprise plan carries
a 99.9% monthly uptime SLA. If uptime falls below that threshold in a given
month, affected customers receive a service credit equal to 10% of that
month's fees for each additional full percentage point of downtime beyond
the SLA, capped at 50% of the monthly fee. Service credits must be
requested within 30 days of the end of the affected month.

## Integrations Marketplace

How many integrations can I enable? There is no limit on the number of
marketplace integrations a workspace can enable. Custom-built integrations
using the platform's API are subject to the plan's standard API rate
limits, the same limits that apply to any other API usage on the account.
