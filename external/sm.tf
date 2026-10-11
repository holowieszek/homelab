module "general_credentials_secrets" {
  source      = "./modules/secrets-manager/v1"
  secret_name = replace(format("%s-general-credentials", module.default_label.id), "-", "/")
  description = "Homelab shared application credentials"

  tags = {
    "managed-by" = "external-secrets"
  }
}

module "global_config_secrets" {
  source      = "./modules/secrets-manager/v1"
  secret_name = replace(format("%s-global-config", module.default_label.id), "-", "/")
  description = "Homelab global configuration"
}
