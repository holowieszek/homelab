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