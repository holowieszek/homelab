resource "aws_iam_user" "this" {
  name = var.name
  tags = var.tags
}

resource "aws_iam_user_policy" "this" {
  name   = format("%s-policy", var.name)
  user   = aws_iam_user.this.name
  policy = var.policy
}