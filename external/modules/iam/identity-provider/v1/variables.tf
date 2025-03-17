variable "name" {
  description = "OIDC provider name"
  type        = string
}

variable "url" {
  description = "URL of the identity provider"
  type        = string
}

variable "client_id_list" {
  description = "List of client IDs (audiences) that identify the application registered with the OIDC provider"
  type        = list(string)
}

variable "thumbprints" {
  description = "List of server certificate thumbprints for the OIDC identity provider's server certificate(s)"
  type        = list(string)
}

variable "policy" {
  description = "The policy document to attach to the OIDC provider role"
  type        = any
}

variable "allowed_repositories" {
  description = "List of repositories allowed to assume web identity with the OIDC provider"
  type        = list(string)
}