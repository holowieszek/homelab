module "ecr_token_helper" {
  source = "./modules/ecr/public/v1"

  name = format("%s-ecr-token-helper", module.default_label.id)
}

module "ecr_kingsmith" {
  source = "./modules/ecr/private/v1"

  name       = format("%s-kingsmith", module.default_label.id)
  mutability = "MUTABLE"
}

module "ecr_weather_station" {
  source = "./modules/ecr/private/v1"

  name       = format("%s-weather-station", module.default_label.id)
  mutability = "MUTABLE"
}