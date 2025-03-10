module "default_label" {
  source  = "cloudposse/label/null"
  version = "0.25.0"

  name        = var.project_name
  environment = var.environment

  label_order      = ["name", "environment"]
  delimiter        = "-"
  label_value_case = "lower"

  tags = {
    Name = var.project_name
  }
}