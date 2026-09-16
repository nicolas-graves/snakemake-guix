MAKEFILE_FLAGS += --always-make

profile:
	mkdir -p .guix-profile
	guix pull --allow-downgrades --disable-authentication --channels=./channels.scm --profile=.guix-profile/guix

build:
	.guix-profile/guix/bin/guix build -f guix.scm -K

install:
	.guix-profile/guix/bin/guix install -L .guix/modules snakemake-guix-remote-execution

test:
	pytest -q deployment/tests
	pytest -q -c executor/pyproject.toml executor/tests

development-shell:
	guix shell -D --file=guix.scm
