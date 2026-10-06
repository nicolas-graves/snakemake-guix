;; Copyright © 2026 Nicolas Graves <ngraves@ngraves.fr>

(define-module (guix-openstack packages)
  #:use-module ((guix licenses) #:prefix license:)
  #:use-module (guix gexp)
  #:use-module (guix git-download)
  #:use-module (guix packages)
  #:use-module (guix build-system pyproject)
  #:use-module (gnu packages python-build)
  #:use-module (gnu packages python)
  #:use-module (gnu packages check)
  #:use-module (gnu packages openstack)
  #:use-module (snakemake-guix packages)
  #:use-module (ice-9 ftw)
  #:use-module (srfi srfi-1)
  #:use-module (srfi srfi-13)
  #:export (python-snakemake-executor-plugin-guix-openstack))

(define %plugin-source-root
  (canonicalize-path
   (string-append
    (dirname (search-path %load-path "guix-openstack/packages.scm"))
    "/../../..")))

(define (plugin-source-file? file _stat)
  (let* ((relative (string-drop file (+ (string-length %plugin-source-root) 1)))
         (directory? (lambda (directory)
                       (or (string=? relative directory)
                           (string-prefix? (string-append directory "/")
                                           relative)))))
    (or (member relative '("LICENSE" "README.md" "pyproject.toml"))
        (directory? "scripts")
        (directory? "src")
        (directory? "tests"))))

(define-public python-snakemake-executor-plugin-guix-openstack
  (package
    (name "python-snakemake-executor-plugin-guix-openstack")
    (version "0.2.0")
    (source
     (local-file "../../../" (git-file-name name version)
                 #:recursive? #t
                 #:select? plugin-source-file?))
    (build-system pyproject-build-system)
    (arguments
     (list #:tests? #t))
    (native-inputs (list python-hatchling python-pytest))
    (propagated-inputs
     (list python
           python-snakemake-executor-plugin-guix-ssh
           python-openstacksdk))
    (home-page "https://github.com/nicolas-graves/snakemake-executor-plugin-guix-openstack")
    (synopsis "Run Guix Snakemake jobs on ephemeral OpenStack instances")
    (description
     "This executor creates one tagged OpenStack worker per Snakemake run,
transfers Guix closures through guix-ssh, retrieves job results, and removes
the instance when the run finishes.")
    (license license:gpl3+)))

python-snakemake-executor-plugin-guix-openstack
