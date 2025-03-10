;; Copyright © 2025 Nicolas Graves <ngraves@ngraves.fr>

(define-module (snakemake-guix-channel)
  #:use-module (git)
  #:use-module (guix build-system pyproject)
  #:use-module (guix build-system python)
  #:use-module (guix gexp)
  #:use-module (guix git-download)
  #:use-module ((guix licenses) #:prefix license:)
  #:use-module (guix packages)
  #:use-module (gnu packages check)
  #:use-module (gnu packages package-management)
  #:use-module (gnu packages python)
  #:use-module (gnu packages python-build)
  #:use-module (gnu packages python-science))

(define-public python-snakemake-deployment-plugin-guix
  (let* ((source-dir (dirname (dirname (dirname (current-filename)))))
         (repo (repository-open source-dir))
         (commit (oid->string (object-id (revparse-single repo "HEAD")))))
    (package
      (name "python-snakemake-deployment-plugin-guix")
      (version "0.1.0")
      (source (local-file source-dir
                          #:recursive? #t
                          #:select? (git-predicate source-dir)))
      (build-system pyproject-build-system)
      (arguments
       (list #:test-flags #~(list "-k" "not test_deploy")))
      (native-inputs (list guix python-flit-core python-pytest))
      (propagated-inputs
       (list snakemake
             python-snakemake-interface-software-deployment-plugins))
      (home-page "\
https://github.com/nicolas-graves/snakemake-deployment-plugin-guix")
      (synopsis "In development")
      (description "In development")
      (license license:gpl3+))))

python-snakemake-deployment-plugin-guix
