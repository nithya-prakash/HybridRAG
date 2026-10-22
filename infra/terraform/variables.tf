variable "region" {
  description = "AWS region."
  type        = string
  default     = "eu-central-1"
}

variable "name" {
  description = "Prefix for resource names."
  type        = string
  default     = "hybridrag"
}

variable "instance_type" {
  description = "EC2 size. The prod compose stack runs Postgres, Redis, Qdrant, Ollama, the API, a Celery worker and the frontend, so it needs 8 GB (t3.large). Use t3.medium only with CHAT_PROVIDER=groq/openai and no Ollama."
  type        = string
  default     = "t3.large"
}

variable "root_volume_gb" {
  description = "Root EBS volume size (holds Postgres, Qdrant and Ollama volumes)."
  type        = number
  default     = 40
}

variable "allowed_cidrs" {
  description = "CIDR blocks allowed to reach the frontend (3000) and API (8000). Restrict to your own IP for anything but a short demo."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "repo_url" {
  description = "Git URL cloned onto the instance."
  type        = string
  default     = "https://github.com/nithya-prakash/HybridRAG.git"
}

variable "repo_ref" {
  description = "Branch or tag to deploy."
  type        = string
  default     = "main"
}

variable "env_parameter_name" {
  description = "SSM Parameter Store SecureString holding the full production .env file. Created by hand (see README) so secrets never enter Terraform state."
  type        = string
  default     = "/hybridrag/prod/env"
}

variable "monthly_budget_usd" {
  description = "Budget alert threshold in USD."
  type        = number
  default     = 30
}

variable "budget_alert_email" {
  description = "Email that receives budget alerts."
  type        = string
}
