module "speedtest_db_secrets" {
  source      = "./modules/secrets-manager/v1"
  secret_name = replace(format("%s-databases-speedtest-credentials", module.default_label.id), "-", "/")
  description = "Homelab Speedtest PostgreSQL database credentials (push)"
}

module "speedtest_app_secrets" {
  source      = "./modules/secrets-manager/v1"
  secret_name = replace(format("%s-applications-speedtest-credentials", module.default_label.id), "-", "/")
  description = "Homelabs Speedtest credentials"
}

module "cert_manager_app_secrets" {
  source      = "./modules/secrets-manager/v1"
  secret_name = replace(format("%s-applications-certmanager-credentials", module.default_label.id), "-", "/")
  description = "Homelab Cert-Manager credentials"
}

module "argocd_app_secrets" {
  source      = "./modules/secrets-manager/v1"
  secret_name = replace(format("%s-applications-argocd-credentials", module.default_label.id), "-", "/")
  description = "Homelab ArgoCD credentials (push)"
}

module "global_config_secrets" {
  source      = "./modules/secrets-manager/v1"
  secret_name = replace(format("%s-global-config", module.default_label.id), "-", "/")
  description = "Homelab global configuration"
}