.PHONY: *

# external is pre-deployed due to the raspberry pi performance issues (terraform-ls)
# default: bare external system

default: bare system

bare:
	make -C bare

external:
	make -C external

system:
	make -C system
	
clean-up:
	docker compose --project-directory ./bare/roles/pxe_server/files down
