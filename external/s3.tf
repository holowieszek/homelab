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

module "volume_backups" {
  source = "./modules/s3/v1"

  bucket_name = format("%s-volume-backups", module.default_label.id)
  acl         = "private"

  versioning_status       = "Enabled"
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

module "opnsense_backups" {
  source = "./modules/s3/v1"

  bucket_name = format("%s-opnsense-backups", module.default_label.id)
  acl         = "private"

  versioning_status       = "Enabled"
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

module "frigate_syncs" {
  source = "./modules/s3/v1"

  bucket_name = format("%s-frigate-syncs", module.default_label.id)
  acl         = "private"

  versioning_status       = "Enabled"
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
