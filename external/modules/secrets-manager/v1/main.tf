resource "aws_secretsmanager_secret" "secret" {
  name                    = var.secret_name
  description             = var.description
  recovery_window_in_days = var.recovery_window_in_days
}
