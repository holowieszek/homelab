TRANSPORT ?= local

default: boot cluster

boot:
	ansible-playbook --inventory inventories/prod.yml boot.yml

cluster:
	ansible-playbook --inventory inventories/prod.yml cluster.yml

configure-check:
	test -n "$(HOSTS)" || (echo "Set HOSTS explicitly"; exit 2)
	ansible-playbook --inventory inventories/prod.yml configure.yml --limit "$(HOSTS)" --check -e maintenance_configure_approved=true

patch-preview:
	test -n "$(HOSTS)" || (echo "Set HOSTS explicitly"; exit 2)
	ansible-playbook --inventory inventories/prod.yml patch-os.yml --limit "$(HOSTS)" --check -e maintenance_authorized=true

patch-apply:
	test -n "$(HOSTS)" || (echo "Set HOSTS explicitly"; exit 2)
	test "$(APPROVED)" = "yes" || (echo "Set APPROVED=yes after operator review"; exit 2)
	ansible-playbook --inventory inventories/prod.yml patch-os.yml --limit "$(HOSTS)" -e maintenance_authorized=true

reboot:
	test -n "$(HOSTS)" || (echo "Set HOSTS explicitly"; exit 2)
	test "$(APPROVED)" = "yes" || (echo "Set APPROVED=yes after operator review"; exit 2)
	ansible-playbook --inventory inventories/prod.yml reboot.yml --limit "$(HOSTS)" -e maintenance_authorized=true -e reboot_authorized=true

osquery-audit:
	test -n "$(CATEGORY)" || (echo "Set CATEGORY explicitly"; exit 2)
	test -n "$(ALIAS)" || (echo "Set ALIAS explicitly"; exit 2)
	test -n "$(ROLE)" || (echo "Set ROLE explicitly"; exit 2)
	test -n "$(OUT)" || (echo "Set private OUT path outside repository"; exit 2)
	python3 ../audit/collect.py --category "$(CATEGORY)" --host-alias "$(ALIAS)" --host-role "$(ROLE)" --commit "$$(git rev-parse HEAD)" --transport "$(TRANSPORT)" --output "$(OUT)"

drift-report:
	test -n "$(DESIRED)" || (echo "Set DESIRED explicitly"; exit 2)
	test -n "$(OBSERVED)" || (echo "Set OBSERVED explicitly"; exit 2)
	python3 ../audit/drift.py "$(DESIRED)" "$(OBSERVED)" $(if $(EXCEPTIONS),--exceptions "$(EXCEPTIONS)")
