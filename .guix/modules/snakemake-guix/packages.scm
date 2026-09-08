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
  #:use-module (gnu packages emacs-xyz)
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

(define-public python-snakemake-interface-common
  (package/inherit guix:python-snakemake-interface-common
    (name "python-snakemake-interface-common")
    (version "1.23.1")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
              (url (string-append "https://github.com/snakemake/"
                                  "snakemake-interface-common"))
              (commit (string-append "v" version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "0pda0qcwg5gcbhpff5ax69m8yhkcf01m9c4dcprp99mg424xabl5"))))))

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
    (propagated-inputs (list python-snakemake-interface-common))))

(define-public python-snakemake-interface-software-deployment-plugins
  ((package-input-rewriting/spec
    `(("python-snakemake-interface-common" .
       ,(const python-snakemake-interface-common))))
   (package/inherit guix:python-snakemake-interface-software-deployment-plugins
     (name "python-snakemake-interface-software-deployment-plugins")
     (version "0.19.1")
     (source
      (origin
        (method git-fetch)
        (uri (git-reference
               (url (string-append "https://github.com/snakemake/"
                                   "snakemake-interface-software-deployment-plugins"))
               (commit (string-append "v" version))))
        (file-name (git-file-name name version))
        (sha256
         (base32 "0axs0f75kgl5bjnszl0dcz1pnxnfl1vihsjwc89ra2l7gfdx9757")))))))

(define-public python-snakemake-storage-plugin-http
  ((package-input-rewriting/spec
    `(("python-snakemake-interface-common" .
       ,(const python-snakemake-interface-common))))
   (package/inherit guix:python-snakemake-storage-plugin-http)))

(define-public snakemake-with-software-deployment
  ;; Commit of branch feat/software-deployment-plugins
  (let ((commit "d1c87fcb9016b27843d7f96fcae699e9d303a705")
        (revision "1"))
    ((package-input-rewriting/spec
      `(("python-snakemake-interface-common" .
         ,(const python-snakemake-interface-common))))
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
           (base32 "082ywypqx9k76jra8zx09krwn1qjscpx8p2js0nymvj5xxdjxs8b"))
          (patches
           (snakemake-guix-patches "snakemake-4009.patch"
                                   "snakemake-allow-without-conda.patch"
                                   "snakemake-record-software-structured.patch"))))
       (propagated-inputs
        (modify-inputs (package-propagated-inputs guix:snakemake)
          (replace "python-snakemake-interface-report-plugins"
            python-snakemake-interface-report-plugins)
          (replace "python-snakemake-interface-software-deployment-plugins"
            python-snakemake-interface-software-deployment-plugins)))
       (native-inputs
        (modify-inputs (package-native-inputs guix:snakemake)
          (append python-pytest
                  python-setuptools-scm
                  guix:python-snakemake-software-deployment-plugin-container
                  guix:python-snakemake-software-deployment-plugin-envmodules)))))))

(define-public python-snakemake-software-deployment-plugin-guix
  (package
    (name "python-snakemake-software-deployment-plugin-guix")
    (version "0.3.3")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
              (url "https://github.com/nicolas-graves/snakemake-guix")
              (commit version)))
       (file-name (git-file-name name version))
       (sha256
        (base32 "17gvzjkl7n1isgz9r73chpyn70aq2ipnibc70lz2awq0cmy9mhkx"))))
    (build-system pyproject-build-system)
    (arguments
     ;; XXX: We would need access to builds with the guile daemon to be able
     ;; to run those.
     (list #:tests? #f))
    (native-inputs
     (list guix python-flit-core python-pytest))
    (propagated-inputs
     (list snakemake-with-software-deployment
           python-snakemake-interface-software-deployment-plugins))
    (home-page "https://github.com/nicolas-graves/snakemake-guix")
    (synopsis "Run Snakemake within a Guix shell or time-machine")
    (description "This package provides a software deployment plugin for Snakemake
using Guix command-line calls.")
    (license license:gpl3+)))

python-snakemake-software-deployment-plugin-guix
