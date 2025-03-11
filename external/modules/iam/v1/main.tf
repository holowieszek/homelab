resource "aws_iam_user" "this" {
  name = var.name
  tags = var.tags
}

resource "aws_iam_policy" "this" {
  name   = format("%s-policy", var.name)
  policy = var.policy
}

resource "aws_iam_user_policy_attachment" "this" {
  user       = aws_iam_user.this.name
  policy_arn = aws_iam_policy.this.arn
}