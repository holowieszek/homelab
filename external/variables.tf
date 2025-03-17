variable "aws_account_number" {
  type        = string
  description = "Target AWS account"
}

variable "region" {
  type        = string
  description = "Target AWS region"
}

variable "project_name" {
  type        = string
  default     = "homelab"
  description = "Project/service name"
}

variable "environment" {
  type        = string
  description = "Environment label that is added to resources"
}

variable "hosted_zone_domain_name" {
  type        = string
  description = "The domain name to create the Route53 zone for"
}

variable "github_oidc_audiences" {
  description = "List of client IDs (audiences) that identify the application registered with the OIDC provider"
  type        = list(string)
}

variable "github_oidc_repositories" {
  description = "List of Github repositories (actions) allowed to assume web identity with the OIDC provider"
  type        = list(string)
}