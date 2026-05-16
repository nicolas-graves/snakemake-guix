;; Copyright © 2026 Nicolas Graves <ngraves@ngraves.fr>

(define-module (snakemake-guix features)
  ;; #:autoload (rde predicates) (ensure-pred)
  #:autoload (rde features) (make-feature)
  #:use-module (gnu services)
  #:use-module (gnu home services)
  #:use-module (gnu packages emacs-xyz)
  #:use-module (guix diagnostics)
  #:use-module (guix gexp)
  #:use-module (snakemake-guix packages)
  #:export (feature-snakemake))

(define* (feature-snakemake
          #:key
          (snakemake snakemake-with-software-deployment)
          (emacs-snakemake-mode emacs-snakemake-mode)
          (snakemake-plugins (list python-snakemake-storage-plugin-http)))
  "Configure and set up tooling for Snakemake."
  ;; XXX: Hiding those which are macros and not procedures, hence not
  ;; #:autoload friendly.
  ;; (ensure-pred file-like? snakemake)
  ;; (ensure-pred file-like? emacs-snakemake-mode)
  ;; (ensure-pred list-of-file-like? snakemake)

  (define f-name 'snakemake)

  (define (get-home-services config)
    "Return home services related to Snakemake."
    (append
     (list
      (simple-service 'add-snakemake-home-packages home-profile-service-type
        (append (list snakemake)
                snakemake-plugins
                (if (get-value 'emacs config #f)
                    (list emacs-snakemake-mode)
                    (list)))))))

  ;; XXX: See the previous commit for the canonical syntax.
  ((@@ (rde features) make-feature)
   f-name
   `((,f-name . ,snakemake))
   get-home-services
   (const '())
   (location "./snakemake-guix/features.scm" 13 0)))
