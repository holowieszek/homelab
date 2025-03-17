module "service_account" {
  source = "./modules/iam/user/v1"

  name = format("%s-svc", module.default_label.id)

  policy = data.aws_iam_policy_document.service_account_policy.json
}

data "aws_iam_policy_document" "service_account_policy" {
  statement {
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"
    ]
    resources = [
      module.global_config_secrets.secret_arn,
      module.grafana_app_secrets.secret_arn,
      module.cert_manager_app_secrets.secret_arn,
      module.speedtest_app_secrets.secret_arn,
      module.pihole_app_secrets.secret_arn,
      module.mikrotik_app_secrets.secret_arn,
      module.linkding_app_secrets.secret_arn,
      module.kingsmith_app_secrets.secret_arn,
      module.homelab_private_repo_secrets.secret_arn,
      format("arn:aws:secretsmanager:%s:%s:secret:homelab/%s/databases/speedtest/credentials-*", var.region, var.aws_account_number, var.environment),
      format("arn:aws:secretsmanager:%s:%s:secret:homelab/%s/databases/linkding/credentials-*", var.region, var.aws_account_number, var.environment),
      format("arn:aws:secretsmanager:%s:%s:secret:homelab/%s/databases/kingsmith/credentials-*", var.region, var.aws_account_number, var.environment),
      format("arn:aws:secretsmanager:%s:%s:secret:homelab/%s/applications/argocd/credentials-*", var.region, var.aws_account_number, var.environment),

      // resources not managed by terraform
      format("arn:aws:secretsmanager:%s:%s:secret:k3s/test-*", var.region, var.aws_account_number),
      format("arn:aws:secretsmanager:%s:%s:secret:k3s/test-another-test-*", var.region, var.aws_account_number),
    ]
  }

  statement {
    actions = [
      "secretsmanager:CreateSecret",
      "secretsmanager:TagResource",
      "secretsmanager:PutSecretValue"
    ]
    resources = [
      format("arn:aws:secretsmanager:%s:%s:secret:homelab/%s/databases/speedtest/credentials-*", var.region, var.aws_account_number, var.environment),
      format("arn:aws:secretsmanager:%s:%s:secret:homelab/%s/databases/linkding/credentials-*", var.region, var.aws_account_number, var.environment),
      format("arn:aws:secretsmanager:%s:%s:secret:homelab/%s/databases/kingsmith/credentials-*", var.region, var.aws_account_number, var.environment),
      format("arn:aws:secretsmanager:%s:%s:secret:homelab/%s/applications/argocd/credentials-*", var.region, var.aws_account_number, var.environment),
    ]
  }

  statement {
    actions = [
      "s3:ListBucket"
    ]
    resources = [
      module.database_backups.bucket_arn,
      module.volume_backups.bucket_arn
    ]
  }

  statement {
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = [
      format("%s/*", module.database_backups.bucket_arn),
      format("%s/*", module.volume_backups.bucket_arn)
    ]
  }

  statement {
    actions = [
      "route53:ListHostedZonesByName"
    ]
    resources = ["*"]
  }

  statement {
    actions = [
      "route53:GetChange"
    ]
    resources = [
      "arn:aws:route53:::change/*"
    ]
  }

  statement {
    actions = [
      "route53:ChangeResourceRecordSets",
      "route53:ListResourceRecordSets"
    ]
    resources = [
      format("arn:aws:route53:::hostedzone/%s", module.primary_hosted_zone.zone_id)
    ]
  }

  statement {
    actions = [
      "ecr:GetAuthorizationToken"
    ]
    resources = ["*"]
  }

  statement {
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage"
    ]
    resources = [
      format("arn:aws:ecr:%s:%s:repository/kingsmith-poc", var.region, var.aws_account_number),
    ]
  }
}