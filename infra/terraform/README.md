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

1. Store the production env file as a SecureString (secrets never enter Terraform state):
   ```bash
   cp ../../.env.prod.example prod.env   # fill in every blank value
   aws ssm put-parameter --name /hybridrag/prod/env --type SecureString \
     --value file://prod.env --region eu-central-1
   rm prod.env
   ```
2. Apply:
   ```bash
   terraform init
   terraform plan  -var budget_alert_email=you@example.com -var 'allowed_cidrs=["YOUR.IP/32"]'
   terraform apply -var budget_alert_email=you@example.com -var 'allowed_cidrs=["YOUR.IP/32"]'
   ```
3. Wait a few minutes (first boot builds images and pulls the Ollama model), then open `frontend_url`.
   Bootstrap log: `aws ssm start-session --target <id>` then `tail -f /var/log/hybridrag-bootstrap.log`.

## Cost and teardown

A `t3.large` plus EIP and 40 GB EBS is roughly 70 to 80 USD per month if left running. The free
tier does not cover it. Run `terraform destroy` when you finish a demo. The S3 bucket must be
empty first (it is versioned), so empty it with `aws s3 rm s3://<bucket> --recursive` and delete
old versions if needed.

## Known limits

- Plain HTTP on 3000/8000. Add a domain plus a TLS terminator (Caddy or an ALB) before real users.
- Single instance, no HA. Postgres/Qdrant data live on the EBS volume; no automated backups yet.
- Existing local-disk uploads are not migrated. Switch backends on a fresh deployment.
