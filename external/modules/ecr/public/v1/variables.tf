variable "name" {
  description = "The name of the public ECR repository"
  type        = string
}

variable "tags" {
  description = "A map of tags to assign to the public ECR repository"
  type        = map(string)
  default     = {}
}