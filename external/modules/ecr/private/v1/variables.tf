variable "name" {
  description = "The name of the public ECR repository"
  type        = string
}

variable "mutability" {
  description = "The tag mutability setting for the repository"
  type        = string
  default     = "INMUTABLE"
}

variable "force_delete" {
  description = "Determines if repository is deleted even if it contains images"
  type        = bool
  default     = false
}

variable "scan_on_push" {
  description = "Whether images are scanned after being pushed to the repository"
  type        = bool
  default     = true
}

variable "tags" {
  description = "A map of tags to assign to the public ECR repository"
  type        = map(string)
  default     = {}
}