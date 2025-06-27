module "opnsense_backups_service_account" {
  source = "./modules/iam/user/v1"

  name = format("%s-opnsense-backups-svc", module.default_label.id)

  policy = data.aws_iam_policy_document.opnsense_backups_service_account_policy.json

}

module "service_account" {
  source = "./modules/iam/user/v1"

  name = format("%s-svc", module.default_label.id)

  policy = data.aws_iam_policy_document.service_account_policy.json
}

data "aws_iam_policy_document" "opnsense_backups_service_account_policy" {
  statement {
    actions = [
      "s3:ListBucket"
    ]
    resources = [
      module.opnsense_backups.bucket_arn,
    ]
  }

  statement {
    actions = [
      "s3:PutObject"
    ]
    resources = [
      format("%s/*", module.opnsense_backups.bucket_arn)
    ]
  }
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
      module.opnsense_backups_app_secrets.secret_arn,
      format("arn:aws:secretsmanager:%s:%s:secret:homelab/%s/databases/speedtest/credentials-*", var.region, var.aws_account_number, var.environment),
      format("arn:aws:secretsmanager:%s:%s:secret:homelab/%s/databases/linkding/credentials-*", var.region, var.aws_account_number, var.environment),
      format("arn:aws:secretsmanager:%s:%s:secret:homelab/%s/databases/kingsmith/credentials-*", var.region, var.aws_account_number, var.environment),
      format("arn:aws:secretsmanager:%s:%s:secret:homelab/%s/databases/weatherstation/credentials-*", var.region, var.aws_account_number, var.environment),
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
      format("arn:aws:secretsmanager:%s:%s:secret:homelab/%s/databases/weatherstation/credentials-*", var.region, var.aws_account_number, var.environment),
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
      module.ecr_kingsmith.arn,
      module.ecr_weather_station.arn,
    ]
  }
}

module "oidc_github" {
  source = "./modules/iam/identity-provider/v1"

  name                 = format("%s-github-oidc", module.default_label.id)
  url                  = "https://token.actions.githubusercontent.com"
  client_id_list       = var.github_oidc_audiences
  thumbprints          = ["d89e3bd43d5d909b47a18977aa9d5ce36cee184c"]
  allowed_repositories = var.github_oidc_repositories
  policy               = data.aws_iam_policy_document.oidc_github.json
}

data "aws_iam_policy_document" "oidc_github" {
  statement {
    actions = [
      "ecr:GetAuthorizationToken",
      "ecr-public:GetAuthorizationToken"
    ]
    resources = ["*"]
  }

  statement {
    actions = [
      "sts:GetServiceBearerToken"
    ]

    resources = ["*"]
    # condition {
    #   test = "StringEquals"
    #   variable = "sts:AWSServiceName"

    #   values = ""
    # }
  }

  statement {
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart"
    ]

    resources = [
      module.ecr_kingsmith.arn,
      module.ecr_weather_station.arn,
    ]
  }

  statement {
    actions = [
      "ecr-public:BatchCheckLayerAvailability",
      "ecr-public:CompleteLayerUpload",
      "ecr-public:InitiateLayerUpload",
      "ecr-public:PutImage",
      "ecr-public:UploadLayerPart"
    ]

    resources = [
      module.ecr_token_helper.arn,
      module.ecr_opnsense_backup_tool.arn
    ]
  }
}
