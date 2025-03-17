provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}

resource "aws_ecrpublic_repository" "this" {
  provider = aws.us_east_1

  repository_name = var.name
  tags            = var.tags
}