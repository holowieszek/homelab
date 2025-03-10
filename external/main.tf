terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = ""
    key            = ""
    region         = ""
    dynamodb_table = ""
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = module.default_label.tags
  }
}