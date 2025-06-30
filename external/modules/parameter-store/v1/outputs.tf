output "parameter_arn" {
  description = "The ARN of the parameter"
  value       = aws_ssm_parameter.main.arn
}

output "secret_name" {
  description = "The name of the secret"
  value       = aws_ssm_parameter.main.name
}
