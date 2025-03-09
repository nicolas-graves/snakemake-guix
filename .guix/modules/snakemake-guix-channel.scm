;; Copyright © 2025 Nicolas Graves <ngraves@ngraves.fr>

(define-module (snakemake-guix-channel)
  #:use-module (git)
  #:use-module (ice-9 popen)
  #:use-module (ice-9 rdelim)
  #:use-module (guix build utils)
  #:use-module (guix build-system pyproject)
  #:use-module (guix build-system python)
  #:use-module (guix download)
  #:use-module (guix gexp)
  #:use-module (guix git-download)
  #:use-module ((guix licenses) #:prefix license:)
  #:use-module (guix packages)
  #:use-module (guix utils)
  #:use-module (gnu packages check)
  #:use-module (gnu packages python-build)
  #:use-module (gnu packages python-xyz))

(define-public python-snakemake-interface-common
  (package
    (name "python-snakemake-interface-common")
    (version "1.17.4")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
             (url "https://github.com/snakemake/snakemake-interface-common")
             (commit (string-append "v" version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "19fyqs048zdvrmq5sdayzch850kwsyv2x6xn57cjjzcm4zpjrh9w"))))
    (build-system pyproject-build-system)
    (arguments
     (list #:phases
           #~(modify-phases %standard-phases
               (replace 'check
                 (lambda* (#:key tests? #:allow-other-keys)
                   (when tests?
                     (invoke "python3" "tests/tests.py")))))))
    (native-inputs (list python-poetry-core python-pytest))
    (propagated-inputs (list python-argparse-dataclass python-configargparse))
    (home-page "https://github.com/snakemake/snakemake-interface-common")
    (synopsis "Common functions and classes for Snakemake and its plugins")
    (description "Common functions and classes for Snakemake and its plugins.")
    (license license:expat)))

(define-public python-argparse-dataclass
  (package
    (name "python-argparse-dataclass")
    (version "2.0.0")
    (source
     (origin
       (method url-fetch)
       (uri (pypi-uri "argparse_dataclass" version))
       (sha256
        (base32 "0zr9r4n00x2wi5kyzw3bxvrdp5k113jw7f9p4f414bsaj4f69aq9"))))
    (build-system pyproject-build-system)
    (native-inputs (list python-setuptools python-wheel))
    (home-page "https://github.com/mivade/argparse_dataclass")
    (synopsis "Declarative CLIs with argparse and dataclasses")
    (description "Declarative CLIs with argparse and dataclasses.")
    (license license:expat)))

(define-public python-snakemake-interface-software-deployment-plugins
  (package
    (name "python-snakemake-interface-software-deployment-plugins")
    (version "0.6.1")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
             (url "https://github.com/snakemake/snakemake-interface-software-deployment-plugins")
             (commit (string-append "v" version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "0b4kkznfyfck9f92pkimhyl13ljisfn67rsilm1a5inq2ywpmxba"))))
    (build-system pyproject-build-system)
    (arguments
     (list #:phases
           #~(modify-phases %standard-phases
               ;; Guix upstream is still at python 3.10
               (add-after 'unpack 'patch-python-3.10
                 (lambda _
                   (substitute* "snakemake_interface_software_deployment_plugins/__init__.py"
                     (("( ->|,) Self") ""))))
               (replace 'check
                 (lambda* (#:key tests? #:allow-other-keys)
                   (when tests?
                     (invoke "python3" "tests/tests.py")))))))
    (propagated-inputs (list python-argparse-dataclass
                             python-snakemake-interface-common))
    (native-inputs (list python-poetry-core))
    (home-page "https://github.com/snakemake/snakemake-interface-software-deployment-plugins")
    (synopsis
     "Interface for interactions between Snakemake and its software deployment plugins.")
    (description
     "This package provides a stable interface for interactions between Snakemake and
its software deployment plugins.")
    (license license:expat)))

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
      (native-inputs (list python-flit-core python-pytest))
      (propagated-inputs (list snakemake
                               python-snakemake-interface-software-deployment-plugins))
      (home-page "https://github.com/nicolas-graves/snakemake-deployment-plugin-guix")
      (synopsis "In development")
      (description "In development")
      (license license:gpl3+))))

python-snakemake-deployment-plugin-guix
