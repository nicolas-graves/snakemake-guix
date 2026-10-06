;; Copyright © 2026 Nicolas Graves <ngraves@ngraves.fr>

(define-module (guix-openstack worker)
  #:use-module (gnu)
  #:use-module (gnu services shepherd)
  #:use-module (gnu services ssh)
  #:use-module (gnu services networking)
  #:use-module (gnu services base)
  #:use-module (gnu packages bash)
  #:use-module (gnu packages base)
  #:use-module (gnu packages linux)
  #:use-module (gnu packages rsync)
  #:use-module (gnu packages ssh)
  #:use-module (guix gexp)
  #:use-module (gnu system linux-initrd)
  #:use-module (snakemake-guix packages)
  #:use-module (ice-9 textual-ports)
  #:use-module (srfi srfi-13)
  #:export (guix-openstack-worker-os))

(define (console-host-key-service)
  (let ((print-host-key
         (program-file
          "guix-openstack-print-host-key"
          #~(begin
              (use-modules (ice-9 textual-ports))
              (call-with-output-file "/dev/ttyS0"
                (lambda (console)
                  (display "SGO-HOSTKEY-BEGIN\n" console)
                  (call-with-input-file "/etc/ssh/ssh_host_ed25519_key.pub"
                    (lambda (port) (display (get-string-all port) console)))
                  (display "SGO-HOSTKEY-END\n" console)
                  (force-output console)))))))
    (simple-service
     'guix-openstack-console-host-key
     shepherd-root-service-type
     (list (shepherd-service
            (provision '(guix-openstack-console-host-key))
            (requirement '(sshd))
            (one-shot? #t)
            (documentation "Print the SSH host public key to the serial console.")
            (start #~(make-forkexec-constructor (list #$print-host-key)))
            (stop #~(const #f)))))))

(define* (guix-openstack-worker-os #:key authorized-keys signing-keys)
  (let ((authorized-keys-file
         (plain-file "guix-openstack-authorized-keys"
                     (string-append (string-join authorized-keys "\n") "\n"))))
    (operating-system
     (host-name "guix-worker")
     (timezone "Etc/UTC")
     (locale "en_US.utf8")
     (bootloader
      (bootloader-configuration
       (bootloader grub-bootloader)
       (targets '("/dev/vda"))
       (timeout 1)
       (terminal-outputs '(console serial))
       (terminal-inputs '(console serial))
       (serial-unit 0)
       (serial-speed 115200)))
     (kernel-arguments (cons* "console=tty0" "console=ttyS0,115200n8"
                              %default-kernel-arguments))
     (initrd-modules
      (append '("virtio_pci" "virtio_scsi" "virtio_blk" "virtio_net"
                "virtio_balloon" "virtio_console" "virtio_rng" "virtio_mmio")
              (base-initrd-modules linux-libre)))
     (file-systems
      (cons* (file-system
              (device (file-system-label "Guix_image"))
              (mount-point "/")
              (type "ext4"))
             (file-system
              (device (file-system-label "GNU-ESP"))
              (mount-point "/boot/efi")
              (type "vfat"))
             %base-file-systems))
     (packages
      (append (list bash coreutils rsync snakemake
                    python-snakemake-software-deployment-plugin-guix)
              %base-packages))
     (services
      (append
       (list (service dhcpcd-service-type)
             (service openssh-service-type
                      (openssh-configuration
                       (openssh openssh-sans-x)
                       (permit-root-login 'prohibit-password)
                       (password-authentication? #f)
                       (authorized-keys `(("root" ,authorized-keys-file)))))
             (console-host-key-service))
       (modify-services %base-services
         (guix-service-type config =>
                            (guix-configuration
                             (inherit config)
                             (authorized-keys
                              (append %default-authorized-guix-keys
                                      (map (lambda (key) (local-file key))
                                           signing-keys)))))))))
    ))
