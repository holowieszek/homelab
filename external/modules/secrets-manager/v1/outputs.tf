output "secret_arn" {
  description = "The ARN of the secret"
  value       = aws_secretsmanager_secret.secret.arn
}

output "secret_name" {
  description = "The name of the secret"
  value       = aws_secretsmanager_secret.secret.name
}