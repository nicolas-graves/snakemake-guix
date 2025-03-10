MAKEFILE_FLAGS += --always-make

profile:
	mkdir -p .guix-profile
	guix pull --allow-downgrades --disable-authentication --channels=./channels.scm --profile=.guix-profile/guix

build:
	.guix-profile/guix/bin/guix build -f guix.scm -K
