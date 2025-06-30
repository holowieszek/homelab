variable "parameter_name" {
  description = "The name of the parameter"
  type        = string
}

variable "description" {
  description = "The description of the parameter"
  type        = string
  default     = ""
}

variable "value" {
  description = "The value of the parameter"
  type        = string
  default     = "TO_BE_UPDATED"
}

variable "type" {
  description = "Type of the parameter [String, StringList, SecureString]"
  type        = string
  default     = "SecureString"
}

variable "tags" {
  description = "A map of tags to assign to the resource"
  type        = map(string)
  default     = {}
}
