resource "aws_ecr_repository" "this" {
  name                 = var.name
  image_tag_mutability = var.mutability

  force_delete = var.force_delete

  image_scanning_configuration {
    scan_on_push = var.scan_on_push
  }
}