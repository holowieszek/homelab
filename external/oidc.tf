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
      module.ecr_kingsmith.arn
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
    ]
  }
}