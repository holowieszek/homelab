resource "aws_s3_bucket" "example" {
  bucket = format("%s-database-backups", module.default_label.id)
}