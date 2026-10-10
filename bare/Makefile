INVENTORY ?= inventories/prod.yml
TRANSPORT ?= local
AUDIT_CATEGORIES ?= os hardware system kernel uptime packages services disks sysctl
SSH_USER ?= ubuntu
SSH_KEY ?= ~/.ssh/test
AUDIT_KEY ?= $(HOME)/.ssh/homelab-audit
ANSIBLE_CONNECT_ARGS = --user "$(SSH_USER)" $(if $(SSH_KEY),--private-key "$(SSH_KEY)",)

default: boot cluster

boot:
	ansible-playbook --inventory "$(INVENTORY)" $(ANSIBLE_CONNECT_ARGS) boot.yml

cluster:
	ansible-playbook --inventory "$(INVENTORY)" $(ANSIBLE_CONNECT_ARGS) cluster.yml

configure-check:
	test -n "$(HOSTS)" || (echo "Set HOSTS explicitly"; exit 2)
	ansible-playbook --inventory "$(INVENTORY)" $(ANSIBLE_CONNECT_ARGS) configure.yml --limit "$(HOSTS)" --check -e maintenance_configure_approved=true

audit-bootstrap:
	test -n "$(HOSTS)" || (echo "Set HOSTS explicitly"; exit 2)
	test "$(APPROVED)" = "yes" || (echo "Set APPROVED=yes after operator review"; exit 2)
	ansible-playbook --inventory "$(INVENTORY)" $(ANSIBLE_CONNECT_ARGS) audit-bootstrap.yml --limit "$(HOSTS)" -e audit_bootstrap_authorized=true -e audit_controller_key_path="$(AUDIT_KEY)"

patch-preview:
	test -n "$(HOSTS)" || (echo "Set HOSTS explicitly"; exit 2)
	ansible-playbook --inventory "$(INVENTORY)" $(ANSIBLE_CONNECT_ARGS) patch-os.yml --limit "$(HOSTS)" --check -e maintenance_authorized=true

patch-apply:
	test -n "$(HOSTS)" || (echo "Set HOSTS explicitly"; exit 2)
	test "$(APPROVED)" = "yes" || (echo "Set APPROVED=yes after operator review"; exit 2)
	ansible-playbook --inventory "$(INVENTORY)" $(ANSIBLE_CONNECT_ARGS) patch-os.yml --limit "$(HOSTS)" -e maintenance_authorized=true

reboot:
	test -n "$(HOSTS)" || (echo "Set HOSTS explicitly"; exit 2)
	test "$(APPROVED)" = "yes" || (echo "Set APPROVED=yes after operator review"; exit 2)
	ansible-playbook --inventory "$(INVENTORY)" $(ANSIBLE_CONNECT_ARGS) reboot.yml --limit "$(HOSTS)" -e maintenance_authorized=true -e reboot_authorized=true

osquery-audit:
	test -n "$(CATEGORY)" || (echo "Set CATEGORY explicitly"; exit 2)
	test -n "$(ALIAS)" || (echo "Set ALIAS explicitly"; exit 2)
	test -n "$(ROLE)" || (echo "Set ROLE explicitly"; exit 2)
	test -n "$(OUT)" || (echo "Set private OUT path outside repository"; exit 2)
	python3 ../audit/collect.py --category "$(CATEGORY)" --host-alias "$(ALIAS)" --host-role "$(ROLE)" --commit "$$(git rev-parse HEAD)" --transport "$(TRANSPORT)" $(if $(SSH_CONFIG),--ssh-config "$(SSH_CONFIG)",) --output "$(OUT)"

osquery-audit-all:
	test -n "$(ALIAS)" || (echo "Set ALIAS explicitly"; exit 2)
	test -n "$(ROLE)" || (echo "Set ROLE explicitly"; exit 2)
	test -n "$(OUT_DIR)" || (echo "Set private OUT_DIR outside repository"; exit 2)
	mkdir -p -m 700 "$(OUT_DIR)"
	status=0; for c in $(AUDIT_CATEGORIES); do \
		python3 ../audit/collect.py --category "$$c" --host-alias "$(ALIAS)" --host-role "$(ROLE)" --commit "$$(git rev-parse HEAD)" --transport "$(TRANSPORT)" $(if $(SSH_CONFIG),--ssh-config "$(SSH_CONFIG)",) --output "$(OUT_DIR)/$$c.json" || status=1; \
	done; exit $$status

drift-report:
	test -n "$(DESIRED)" || (echo "Set DESIRED explicitly"; exit 2)
	test -n "$(OBSERVED)" || (echo "Set OBSERVED explicitly"; exit 2)
	python3 ../audit/drift.py "$(DESIRED)" "$(OBSERVED)" $(if $(EXCEPTIONS),--exceptions "$(EXCEPTIONS)")
