variable "secret_name" {
  description = "The name of the secret"
  type        = string
}

variable "description" {
  description = "The description of the secret"
  type        = string
  default     = ""
}

variable "recovery_window_in_days" {
  description = "The number of days that AWS Secrets Manager waits before it can delete the secret"
  type        = number
  default     = 7
}

variable "tags" {
  description = "A map of tags to assign to the resource"
  type        = map(string)
  default     = {}
}