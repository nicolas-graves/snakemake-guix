;; Copyright © 2025, 2026 Nicolas Graves <ngraves@ngraves.fr>

(define-module (snakemake-guix packages)
  #:use-module (guix build-system emacs)
  #:use-module (guix build-system pyproject)
  #:use-module (guix diagnostics)
  #:use-module (guix download)
  #:use-module (guix gexp)
  #:use-module (guix git-download)
  #:use-module (guix i18n)
  #:use-module ((guix licenses) #:prefix license:)
  #:use-module (guix packages)
  #:use-module ((guix utils) #:select (substitute-keyword-arguments))
  #:use-module (gnu packages)
  #:use-module (gnu packages check)
  #:use-module (gnu packages package-management)
  #:use-module (gnu packages python-build)
  #:use-module ((gnu packages python-science) #:prefix guix:)
  #:use-module (ice-9 match)
  #:use-module (srfi srfi-34)
  #:export (snakemake-guix-patches))

;;; Patch path infrastructure, adapted from nonguix.
;;; 'search-patches' is syntax and cannot be overridden, so we provide
;;; 'snakemake-guix-patches' for patches living under snakemake-guix/patches/.

(define %snakemake-guix-root-directory
  (letrec-syntax ((dirname* (syntax-rules ()
                              ((_ file)
                               (dirname file))
                              ((_ file head tail ...)
                               (dirname (dirname* file tail ...)))))
                  (try      (syntax-rules ()
                              ((_ (file things ...) rest ...)
                               (match (search-path %load-path file)
                                 (#f
                                  (try rest ...))
                                 (absolute
                                  (dirname* absolute things ...))))
                              ((_)
                               #f))))
    (try ("snakemake-guix/packages.scm" snakemake-guix/))))

(define %snakemake-guix-patch-path
  (make-parameter
   (map (lambda (directory)
          (if (string=? directory %snakemake-guix-root-directory)
              (string-append directory "/snakemake-guix/patches")
              directory))
        %load-path)))

(define (search-snakemake-guix-patch file-name)
  (or (search-path (%snakemake-guix-patch-path) file-name)
      (raise (formatted-message (G_ "~a: patch not found") file-name))))

(define-syntax-rule (snakemake-guix-patches file-name ...)
  (list (search-snakemake-guix-patch file-name) ...))

(define-public emacs-snakemake-mode
  (let ((commit "e4751a951a53c4d4610b2eb17469a21177cab6bc")
        (revision "0"))
    (package
      (name "emacs-snakemake-mode")
      (version (git-version "2.0.0" revision commit))
      (source
       (origin
         (method git-fetch)
         (uri (git-reference
                (url "https://git.kyleam.com/snakemake-mode")
                (commit commit)))
         (file-name (git-file-name name version))
         (sha256
          (base32 "0b19bfk2d29v6ckh0sxyrrl8mzqqpmnxbs9rp58rf7ipk4rp6xwl"))))
      (build-system emacs-build-system)
      (arguments
       (list
        ;; XXX: Tests involving the snakemake binary fail.
        #:tests? #f
        #:test-command #~(list "make" "test")))
      (native-inputs (list guix:snakemake))
      (propagated-inputs (list emacs-transient))
      (home-page "https://git.kyleam.com/snakemake-mode")
      (synopsis "Major mode for editing Snakemake files")
      (description
       "This package provides support for editing Snakemake files in Emacs.  It
builds on Python mode to provide fontification, indentation, and imenu indexing
for Snakemake's rule blocks, as well as an interface for running Snakemake
commands and support for highlighting embedded R code.")
      (license license:gpl3+))))

(define-public python-snakemake-interface-report-plugins
  (package/inherit guix:python-snakemake-interface-report-plugins
    (name "python-snakemake-interface-report-plugins")
    (version "2.0.1")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
              (url (string-append "https://github.com/snakemake/"
                                  "snakemake-interface-report-plugins"))
              (commit (string-append "v" version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "0rkbviqaxxc9lajf5rj06xh9acpxkzfsd0v20i9mcjj4wlry0wqf"))))
    (propagated-inputs (list guix:python-snakemake-interface-common))))

(define-public snakemake-with-software-deployment
  ;; Commit of branch feat/software-deployment-plugins
  (let ((commit "2d502d2c6828e1639c21743c812a7e70d3044135")
        (revision "0"))
    (package/inherit guix:snakemake
      (name "snakemake")
      ;; Version of last common commit with master branch
      (version (git-version "9.26.1" revision commit))
      (source
       (origin
         (method git-fetch)
         (uri (git-reference
                (url "https://github.com/snakemake/snakemake")
                (commit commit)))
         (file-name (git-file-name name version))
         (sha256
          (base32 "11d5zpm2gkrgvqlpj539f632np30ydm7w8c8j34wxir3qvfdgn20"))
         (patches
          (snakemake-guix-patches "snakemake-4009.patch"
                                  "snakemake-allow-without-conda.patch"
                                  "snakemake-record-software-structured.patch"))))
      (propagated-inputs
       (modify-inputs (package-propagated-inputs guix:snakemake)
         (replace "python-snakemake-interface-report-plugins"
           python-snakemake-interface-report-plugins)))
      (native-inputs
       (modify-inputs (package-native-inputs guix:snakemake)
         (append python-pytest
                 python-setuptools-scm
                 guix:python-snakemake-software-deployment-plugin-container
                 guix:python-snakemake-software-deployment-plugin-envmodules))))))

(define-public python-snakemake-software-deployment-plugin-guix
  (package
    (name "python-snakemake-software-deployment-plugin-guix")
    (version "0.3.2")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
              (url "https://github.com/nicolas-graves/snakemake-guix")
              (commit version)))
       (file-name (git-file-name name version))
       (sha256
        (base32 "1nm3vwhr6q347yg2in5d9k2srq62v0pdp5g1g4fq6p9m16yrr2mf"))))
    (build-system pyproject-build-system)
    (arguments
     ;; XXX: We would need access to builds with the guile daemon to be able
     ;; to run those.
     (list #:tests? #f))
    (native-inputs
     (list guix python-flit-core python-pytest))
    (propagated-inputs
     (list snakemake-with-software-deployment
           guix:python-snakemake-interface-software-deployment-plugins))
    (home-page "https://github.com/nicolas-graves/snakemake-guix")
    (synopsis "Run Snakemake within a Guix shell or time-machine")
    (description "This package provides a software deployment plugin for Snakemake
using Guix command-line calls.")
    (license license:gpl3+)))

python-snakemake-software-deployment-plugin-guix
