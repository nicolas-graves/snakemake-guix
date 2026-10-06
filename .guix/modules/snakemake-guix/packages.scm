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
  #:use-module (gnu packages databases)
  #:use-module (gnu packages duckdb)
  #:use-module (gnu packages emacs-xyz)
  #:use-module (gnu packages openstack)
  #:use-module (gnu packages package-management)
  #:use-module (gnu packages python)
  #:use-module (gnu packages python-build)
  #:use-module ((gnu packages python-science) #:prefix guix:)
  #:use-module (gnu packages rsync)
  #:use-module (gnu packages ssh)
  #:use-module (gnu packages time)
  #:use-module (gnu packages version-control)
  #:use-module (ice-9 ftw)
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

(define %snakemake-guix-source-root
  (canonicalize-path
   (string-append
    (dirname (search-path %load-path "snakemake-guix/packages.scm"))
    "/../../..")))

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

(define-public snakemake
  ;; Commit merging branch feat/software-deployment-plugins
  (let ((commit "91763d644db0a6051c40014fa8ffad340f7d39a0")
        (revision "2"))
    ((package-input-rewriting/spec
      `(("python-snakemake-interface-common" .
         ,(const python-snakemake-interface-common))))
     (package/inherit guix:snakemake
       (name "snakemake")
       ;; Version of last common commit with master branch
       (version (git-version "9.27.0" revision commit))
       (source
        (origin
          (method git-fetch)
          (uri (git-reference
                 (url "https://github.com/snakemake/snakemake")
                 (commit commit)))
          (file-name (git-file-name name version))
          (sha256
           (base32 "0iby47d69m69gd3kdqnds25dws5jir4459w0gmyihd7665805vv8"))
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
    (version "0.4.1")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
              (url "https://github.com/nicolas-graves/snakemake-guix")
              (commit (string-append
                       "snakemake-software-deployment-plugin-guix-"
                       version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "mtqaoes7narwnbsf3it6uwnisi456nnhgdjcap5a5g7gxkrrws7q"))))
    (build-system pyproject-build-system)
    (arguments
     ;; XXX: We would need access to builds with the guile daemon to be able
     ;; to run those.
     (list
      #:tests? #f
      #:phases
      #~(modify-phases %standard-phases
          (add-after 'unpack 'enter-deployment-source
            (lambda _ (chdir "deployment"))))))
    (native-inputs
     (list guix python-flit-core python-pytest))
    (propagated-inputs
     (list snakemake
           python-snakemake-interface-software-deployment-plugins))
    (home-page "https://github.com/nicolas-graves/snakemake-guix")
    (synopsis "Run Snakemake within a Guix shell or time-machine")
    (description "This package provides a software deployment plugin for Snakemake
using Guix command-line calls.")
    (license license:gpl3+)))

(define-public python-snakemake-executor-plugin-guix-ssh
  (package
    (name "python-snakemake-executor-plugin-guix-ssh")
    (version "0.2.1")
    (source
     (local-file (string-append %snakemake-guix-source-root "/executor")
                 (git-file-name name version)
                 #:recursive? #t))
    (build-system pyproject-build-system)
    (native-inputs (list python-hatchling python-pytest))
    (propagated-inputs
     (list python
           guix
           openssh
           rsync
           snakemake
           guix:python-snakemake-interface-executor-plugins
           python-snakemake-interface-common
           python-snakemake-software-deployment-plugin-guix))
    (home-page "https://github.com/nicolas-graves/snakemake-guix")
    (synopsis "Execute Snakemake jobs over SSH with immutable Guix profiles")
    (description "This Snakemake executor plugin transfers Guix closures and job
files to independent SSH workers while leaving DAG and provenance ownership with
the local Snakemake controller.")
    (license license:gpl3+)))

(define-public python-snakemake-executor-plugin-guix-openstack
  (package
    (name "python-snakemake-executor-plugin-guix-openstack")
    (version "0.2.0")
    (source
     (local-file (string-append %snakemake-guix-source-root "/openstack")
                 (git-file-name name version)
                 #:recursive? #t))
    (build-system pyproject-build-system)
    (arguments (list #:tests? #t))
    (native-inputs (list python-hatchling python-pytest))
    (propagated-inputs
     (list python
           python-snakemake-executor-plugin-guix-ssh
           python-openstacksdk))
    (home-page "https://github.com/nicolas-graves/snakemake-guix")
    (synopsis "Run Guix Snakemake jobs on ephemeral OpenStack instances")
    (description
     "This executor creates one tagged OpenStack worker per Snakemake run,
transfers Guix closures through guix-ssh, retrieves job results, and removes
the instance when the run finishes. Its separate image maintenance command
publishes and reuses immutable private Glance images.")
    (license license:gpl3+)))

(define-public python-duckdb-engine
  (package
    (name "python-duckdb-engine")
    (version "0.17.0")
    (source
     (origin
       (method url-fetch)
       (uri (pypi-uri "duckdb_engine" version))
       (sha256
        (base32 "1kzk137x419d0d05l73irwaq0j4b5di946l8h2m3draljy326srr"))))
    (build-system pyproject-build-system)
    (arguments
     ;; The test suite needs network access and optional dependencies.
     (list #:tests? #f))
    (propagated-inputs (list python-duckdb python-packaging python-sqlalchemy-2))
    (native-inputs (list python-poetry-core))
    (home-page "https://github.com/Mause/duckdb_engine")
    (synopsis "SQLAlchemy driver for DuckDB")
    (description "This package provides a SQLAlchemy dialect for DuckDB.")
    (license license:expat)))

(define %snakemake-storage-plugin-sqlsink-commit
  "c4a8c52e0a028f420ada9161935395e6003a633f")

(define %snakemake-storage-plugin-sqlsink-source
  (origin
    (method git-fetch)
    (uri (git-reference
           (url "https://github.com/nicolas-graves/snakemake-storage-plugin-sqlsink")
           (commit %snakemake-storage-plugin-sqlsink-commit)))
    (file-name (git-file-name "snakemake-storage-plugin-sqlsink" "0.1.0"))
    (sha256
     (base32 "0r85jiv1m1sgji98ng9za1ysanvknhsvggy2lbkq4ldaw81kv8yg"))))

(define-public python-sqlsink
  (package
    (name "python-sqlsink")
    (version "0.1.0")
    (source %snakemake-storage-plugin-sqlsink-source)
    (build-system pyproject-build-system)
    (arguments
     (list
      #:tests? #f
      #:phases
      #~(modify-phases %standard-phases
          (add-after 'unpack 'enter-core-source
            (lambda _ (chdir "workflow/scripts"))))))
    (native-inputs (list python-setuptools))
    (propagated-inputs
     (list python-duckdb
           python-duckdb-engine
           python-psycopg
           python-pytz
           python-sqlalchemy-2))
    (home-page "https://github.com/nicolas-graves/snakemake-storage-plugin-sqlsink")
    (synopsis "Incremental Parquet-to-SQL publishing core")
    (description "This package provides the sqlsink library, which publishes
Parquet datasets into PostgreSQL or DuckDB tables incrementally.")
    (license license:gpl3+)))

(define-public python-snakemake-storage-plugin-sqlsink
  (package
    (name "python-snakemake-storage-plugin-sqlsink")
    (version "0.1.0")
    (source %snakemake-storage-plugin-sqlsink-source)
    (build-system pyproject-build-system)
    (arguments
     (list
      #:tests? #f
      #:phases
      #~(modify-phases %standard-phases
          (add-after 'unpack 'enter-plugin-source
            (lambda _ (chdir "workflow/sql_storage_plugin"))))))
    (native-inputs (list python-setuptools snakemake))
    (propagated-inputs
     (list python-snakemake-interface-common
           python-sqlsink
           guix:python-snakemake-interface-storage-plugins))
    (home-page "https://github.com/nicolas-graves/snakemake-storage-plugin-sqlsink")
    (synopsis "Snakemake storage plugin publishing tables to a SQL database")
    (description "This Snakemake storage plugin uses SQL tables as workflow
outputs, backed by the sqlsink library.")
    (license license:gpl3+)))

(define-public python-snakemake-report-plugin-forge-dag
  (package
    (name "python-snakemake-report-plugin-forge-dag")
    (version "0.1.0")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
              (url "https://github.com/nicolas-graves/snakemake-report-plugin-forge-dag")
              (commit "1fb51320665850ccc9256448d60380a69d0e3ca2")))
       (file-name (git-file-name name version))
       (sha256
        (base32 "18x9pz1inj1kav7rli00gfkawmwhwgxjybpgc0jkz1xgmc153h06"))))
    (build-system pyproject-build-system)
    (arguments
     (list
      #:phases
      #~(modify-phases %standard-phases
          (add-before 'check 'set-home
            ;; Snakemake creates its source cache under $HOME.
            (lambda _ (setenv "HOME" "/tmp"))))))
    ;; The tests run Snakemake on a workflow in a temporary git repository;
    ;; the SVG test is skipped without graphviz.
    (native-inputs (list git-minimal python-pytest python-setuptools snakemake))
    (propagated-inputs
     (list python-snakemake-interface-common
           python-snakemake-interface-report-plugins))
    (home-page "https://github.com/nicolas-graves/snakemake-report-plugin-forge-dag")
    (synopsis "Snakemake report plugin linking DAG nodes to rule sources")
    (description "This Snakemake report plugin draws the job DAG, as
@command{snakemake --dag} does, with each node linked to the line defining its
rule on the git forge hosting it, including rules from included files and from
modules kept in git submodules.")
    (license license:gpl3+)))

(define-public snakemake-guix-remote-execution
  (package
  (inherit snakemake)
  (name "snakemake-guix-remote-execution")
  (propagated-inputs
   (modify-inputs (package-propagated-inputs snakemake)
     (append python-snakemake-software-deployment-plugin-guix
             python-snakemake-executor-plugin-guix-ssh
             python-snakemake-executor-plugin-guix-openstack
             (specification->package
              "python-snakemake-storage-plugin-http"))))))

snakemake-guix-remote-execution
