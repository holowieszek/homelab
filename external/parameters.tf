# let's migrate secrets manager to the parameter store at some point, to reduce cost of the secrets manager
# i don't need all of those fancy features of sm, so there's no need to pay for it 
module "speedtest_app_parameters" {
  source         = "./modules/parameter-store/v1"
  parameter_name = replace(format("/%s-applications-speedtest-credentials", module.default_label.id), "-", "/")
  type           = "SecureString"
}
