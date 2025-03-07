resource "aws_s3_bucket" "database_backups" {
  bucket = format("%s-database-backups", module.default_label.id)
}