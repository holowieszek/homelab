module "database_backups" {
  source = "./modules/s3/v1"

  bucket_name = format("%s-database-backups", module.default_label.id)
  acl         = "private"

  versioning_status       = "Enabled"
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}