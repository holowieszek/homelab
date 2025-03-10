default: provision

provision:
	tofu init --backend-config=config/backend/prod.tfbackend

	tofu plan -var-file=config/environment/prod.tfvars -out=tfplan

	tofu apply tfplan