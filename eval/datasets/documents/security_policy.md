# Information Security Policy

## Password and Authentication Requirements

All employee accounts require a minimum password length of 14 characters,
must not match any of the employee's previous 10 passwords, and expire every
180 days. Multi-factor authentication is mandatory for all accounts with
access to production systems, customer data, or financial systems; SMS-based
MFA is not permitted for these accounts, only authenticator-app or
hardware-key based methods. A locked-out account is automatically unlocked
after 30 minutes, or immediately by IT Security upon identity verification.

## Data Classification

Company data is classified into four tiers: Public, Internal, Confidential,
and Restricted. Restricted data (customer PII, payment card data, and
authentication credentials) may only be stored in approved, encrypted
systems and must never be copied to a personal device or transmitted over
unencrypted channels. Confidential data (unreleased product plans, internal
financials) requires manager approval before being shared outside the
immediate team. Data classification level must be labeled in the header of
any document containing Confidential or Restricted data.

## Encryption Standards

All data at rest is encrypted using AES-256. Data in transit between
services must use TLS 1.2 or higher; TLS 1.0 and 1.1 are disabled on all
production load balancers. Encryption keys are rotated every 90 days and
managed through the company's central key management service, never
hard-coded in application source code or configuration files checked into
version control.

## Access Reviews

Access to production systems and customer data is reviewed quarterly by
each system owner. Any access grant that has not been used in the preceding
60 days is automatically revoked during the review. Employees changing teams
or roles have their access to their previous team's systems revoked within
5 business days of the role change taking effect.

## Vendor Security Review

Any third-party vendor that will process Confidential or Restricted data
must complete a security questionnaire and, for vendors handling Restricted
data, an annual SOC 2 Type II report review before a contract is signed.
Vendor security reviews are valid for 12 months, after which the vendor
must be re-reviewed before contract renewal.

## Security Incident Reporting

Any suspected security incident — a lost device, a phishing email that was
clicked, unauthorized access, or a suspected data leak — must be reported to
the Security team within 1 hour of discovery, using the #security-incidents
channel or the security hotline for after-hours reporting. Employees who
report a security concern in good faith are never subject to disciplinary
action for the report itself, even if the concern turns out to be a false
alarm.

## Offboarding

When an employee's employment ends, all system access is revoked within 4
hours of the offboarding being processed by HR, company equipment must be
returned within 5 business days, and any credentials the employee had access
to that cannot be individually revoked (shared service accounts, for
example) are rotated within 24 hours.

## Physical Security

Office badge access logs are retained for 1 year. Visitors must be
signed in and escorted at all times in areas containing Confidential or
Restricted data. Server room access is limited to members of the
Infrastructure team and requires two-factor physical access (badge plus
PIN).
