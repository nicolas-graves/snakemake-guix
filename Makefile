MAKEFILE_FLAGS += --always-make

profile:
	mkdir -p .guix-profile
	guix pull --allow-downgrades --disable-authentication --channels=./channels.scm --profile=.guix-profile/guix

build:
	.guix-profile/guix/bin/guix build -f guix.scm -K

install:
	.guix-profile/guix/bin/guix install -L .guix/modules python-snakemake-deployment-plugin-guix python-wrapper

development-shell:
	guix shell -D --file=guix.scm
