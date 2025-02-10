.PHONY: *

bare:
	make -C bare

clean-up:
	docker compose --project-directory ./bare/roles/pxe_server/files down
