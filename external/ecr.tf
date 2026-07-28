module "ecr_token_helper" {
  source = "./modules/ecr/public/v1"

  name = format("%s-ecr-token-helper", module.default_label.id)
}

module "ecr_opnsense_backup_tool" {
  source = "./modules/ecr/public/v1"

  name = format("%s-ecr-opnsense-backup-tool", module.default_label.id)
}

module "ecr_cloudlog" {
  source = "./modules/ecr/public/v1"

  name = format("%s-ecr-cloudlog", module.default_label.id)
}

module "ecr_meshcore_telemetry_processor" {
  source = "./modules/ecr/public/v1"

  name = format("%s-ecr-meshcore-telemetry-processor", module.default_label.id)
}
