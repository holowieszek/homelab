.PHONY: *

default: bare system

bare:
	make -C bare

system:
	make -C system
	
clean-up:
	docker compose --project-directory ./bare/roles/pxe_server/files down
