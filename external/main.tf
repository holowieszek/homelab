terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
      aws    = "~> 5.0"
    }
  }

  backend "s3" {
    bucket = ""
    key = ""
    region = ""
    dynamodb_table = ""
  }
}

provider "aws" {
  region = ""

  default_tags {
    tags = module.default_label.tags
  }
}