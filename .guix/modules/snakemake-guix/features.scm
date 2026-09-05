;; Copyright © 2026 Nicolas Graves <ngraves@ngraves.fr>

(define-module (snakemake-guix features)
  ;; #:autoload (rde predicates) (ensure-pred)
  #:autoload (rde features) (get-value make-feature)
  #:autoload (rde serializers yaml) (yaml-serialize)
  #:use-module (gnu services)
  #:use-module (gnu home services)
  #:use-module (gnu packages emacs-xyz)
  #:use-module (guix diagnostics)
  #:use-module (guix gexp)
  #:use-module (snakemake-guix packages)
  #:export (feature-snakemake))

(define* (feature-snakemake
          #:key
          (snakemake snakemake)
          (emacs-snakemake-mode emacs-snakemake-mode)
          (snakemake-plugins
           (list python-snakemake-software-deployment-plugin-guix)))
  "Configure and set up tooling for Snakemake."
  ;; XXX: Hiding those which are macros and not procedures, hence not
  ;; #:autoload friendly.
  ;; (ensure-pred file-like? snakemake)
  ;; (ensure-pred file-like? emacs-snakemake-mode)
  ;; (ensure-pred list-of-file-like? snakemake)

  (define f-name 'snakemake)

  (define (get-home-services config)
    "Return home services related to Snakemake."
    (list
     (simple-service 'add-snakemake-home-packages home-profile-service-type
       (append (list snakemake)
               snakemake-plugins
               (if ((@ (rde features) get-value) 'emacs config #f)
                   (list emacs-snakemake-mode)
                   (list))))
     (simple-service 'add-snakemake-env home-environment-variables-service-type
       '(("SNAKEMAKE_PROFILE" . "default")))
     (simple-service 'add-snakemake-config
         home-xdg-configuration-files-service-type
       `(("snakemake/default/config.yaml"
          ,(mixed-text-file "snakemake-default-config.yaml"
                            ((@ (rde serializers yaml) yaml-serialize)
                             `((cores . all)
                               (software-deployment-method . #(guix))))))))))

  ;; MAKE-FEATURE is a plain keyword procedure (unlike the `feature' macro),
  ;; so it works under #:autoload -- #:autoload only resolves procedures and
  ;; variables, never macros, and every <feature> field it doesn't name here
  ;; still gets a safe default, so future fields added to <feature> don't
  ;; break this call the way they did when this used the raw, positional
  ;; %make-feature-procedure (see git history for that version).
  (make-feature
   #:name f-name
   #:values `((,f-name . ,snakemake))
   #:home-services-getter get-home-services
   #:location (location "./snakemake-guix/features.scm" 13 0)))
