variable "name" {
  description = "The name of the user"
  type        = string
}

variable "tags" {
  description = "A map of tags to assign to the bucket"
  type        = map(string)
  default     = {}
}

variable "policy" {
  description = "The policy document to attach to the user"
  type        = any
}