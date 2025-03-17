resource "aws_iam_openid_connect_provider" "this" {
  url = var.url

  client_id_list = var.client_id_list

  thumbprint_list = var.thumbprints
}

data "aws_iam_policy_document" "this" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.this.arn]
    }

    condition {
      test     = "StringEquals"
      variable = format("%s:aud", trimprefix(var.url, "https://"))

      values = var.client_id_list
    }

    condition {
      test     = "StringLike"
      variable = format("%s:sub", trimprefix(var.url, "https://"))

      values = var.allowed_repositories
    }
  }
}

resource "aws_iam_role" "this" {
  name               = format("%s-role", var.name)
  assume_role_policy = data.aws_iam_policy_document.this.json
}

resource "aws_iam_policy" "this" {
  name   = format("%s-policy", var.name)
  policy = var.policy
}

resource "aws_iam_role_policy_attachment" "test-attach" {
  role       = aws_iam_role.this.name
  policy_arn = aws_iam_policy.this.arn
}