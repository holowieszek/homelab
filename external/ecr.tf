module "ecr_token_helper" {
  source = "./modules/ecr/public/v1"

  name = format("%s-ecr-token-helper", module.default_label.id)
}