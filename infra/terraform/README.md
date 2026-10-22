# HybridRAG on AWS (single EC2 + S3, Terraform)

One EC2 instance runs the existing `docker-compose.prod.yml` stack. Uploads go to a private,
encrypted, versioned S3 bucket through the app's `S3Storage` backend (`STORAGE_BACKEND=s3`).
Auth to S3 is the instance's IAM role, with no access keys anywhere.

| Resource | Purpose |
|---|---|
| `aws_instance` (Amazon Linux 2023, IMDSv2, encrypted gp3) | Runs the compose stack |
| `aws_s3_bucket` + public-access block, SSE, versioning, lifecycle | Document uploads |
| `aws_iam_role` / instance profile | Least-privilege S3 + read one SSM parameter + SSM Session Manager |
| `aws_security_group` | Ports 3000 and 8000 from `allowed_cidrs`; no SSH |
| `aws_eip` | Stable public address |
| `aws_budgets_budget` | Email alert at 80% of the monthly budget |

## Deploy

### 1. Prerequisites

AWS account (MFA on root, a non-root admin user or SSO), then:
```bash
brew install awscli
brew tap hashicorp/tap && brew install hashicorp/tap/terraform
aws configure sso            # or: aws configure
aws sts get-caller-identity  # confirm the account
```

### 2. Prepare the env file

```bash
cp ../../.env.prod.example prod.env   # fill in every blank value (openssl rand -hex 32 for secrets)
```

Two settings need care on this plain-HTTP, IP-addressed demo:

- **`COOKIE_SECURE=false`.** The template says `true`, but browsers will not send secure cookies
  over `http://`, so login would silently fail. The app's startup checks accept `false`. Switch it
  back to `true` once you put a domain and TLS in front.
- **`NEXT_PUBLIC_API_URL` and `CORS_ORIGINS` depend on the Elastic IP, which Terraform creates.**
  `NEXT_PUBLIC_API_URL` is baked into the frontend at build time. Put placeholders in for the first
  pass (for example `http://localhost:8000` and `["http://localhost:3000"]`) and fix them in step 5.

Upload it, then delete the local copy:
```bash
aws ssm put-parameter --name /hybridrag/prod/env --type SecureString \
  --value file://prod.env --region eu-central-1
rm prod.env
```

### 3. Plan and apply

```bash
terraform init
terraform plan  -var budget_alert_email=you@example.com -var 'allowed_cidrs=["YOUR.IP/32"]'
terraform apply -var budget_alert_email=you@example.com -var 'allowed_cidrs=["YOUR.IP/32"]'
```

Find your IP with `curl -s https://checkip.amazonaws.com`. Read the plan first: it should only
create resources. The outputs give `public_ip`, `frontend_url`, `api_url` and an SSM command.

### 4. First boot (10 to 20 minutes)

The instance installs Docker, clones the repo and runs `hybridrag-redeploy`, which builds the
images and pulls the Ollama model. Watch it (needs `brew install --cask session-manager-plugin`):
```bash
aws ssm start-session --target <instance-id> --region eu-central-1
sudo tail -f /var/log/hybridrag-bootstrap.log
```

### 5. Second pass: set the real URLs

Edit the SSM parameter so `NEXT_PUBLIC_API_URL=http://<public_ip>:8000` and
`CORS_ORIGINS=["http://<public_ip>:3000"]`, write it back with `put-parameter --overwrite`, then in
an SSM session run:
```bash
sudo hybridrag-redeploy
```
The script re-reads the parameter, re-adds the S3 settings and rebuilds the frontend.

### 6. Verify

Open `frontend_url`, register, upload a PDF and ask a question. Confirm the upload reached S3:
`aws s3 ls s3://<uploads_bucket>/uploads/ --recursive`, and `curl http://<public_ip>:8000/health`.

## Cost and teardown

The default `m7i-flex.large` (8 GB, x86_64) is on AWS's free-plan eligible list for accounts created
after 15 July 2025, so a short demo should be covered by the sign-up credits (verify the list for your
account and region with `aws ec2 describe-instance-types --filters Name=free-tier-eligible,Values=true`).
It is not free forever: left running past the credits or the 6-month free plan it costs roughly 70 to
80 USD per month with the Elastic IP and 40 GB EBS. `t3.large` is the same size but not eligible.
Run `terraform destroy` as soon as you finish a demo. The S3 bucket must be
empty first (it is versioned), so empty it with `aws s3 rm s3://<bucket> --recursive` and delete
old versions if needed.

## Known limits

- Plain HTTP on 3000/8000. Add a domain plus a TLS terminator (Caddy or an ALB) before real users.
- Single instance, no HA. Postgres/Qdrant data live on the EBS volume; no automated backups yet.
- Existing local-disk uploads are not migrated. Switch backends on a fresh deployment.
