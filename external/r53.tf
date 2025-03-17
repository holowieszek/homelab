module "primary_hosted_zone" {
  source      = "./modules/route53/v1"
  domain_name = var.hosted_zone_domain_name
}