variable "domain_name" {
  description = "The domain name to create the Route53 zone for"
  type        = string
}

variable "tags" {
  description = "Tags to apply to the Route53 zone"
  type        = map(string)
  default     = {}
}