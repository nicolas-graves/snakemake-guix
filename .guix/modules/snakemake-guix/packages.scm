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
  #:use-module (gnu packages emacs-xyz)
  #:use-module (gnu packages package-management)
  #:use-module (gnu packages python)
  #:use-module (gnu packages python-build)
  #:use-module ((gnu packages python-science) #:prefix guix:)
  #:use-module (gnu packages python-web)
  #:use-module (gnu packages python-xyz)
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

(define-public python-sqlmodel
  (package
    (name "python-sqlmodel")
    (version "0.0.37")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
              (url "https://github.com/fastapi/sqlmodel")
              (commit version)))
       (file-name (git-file-name name version))
       (sha256
        (base32 "1kb81a1ffvsvkvi9msblv3sq0s74ww340dxz3rymh5snnxc1pg92"))))
    (build-system pyproject-build-system)
    (arguments
     (list
      #:test-flags
      ;; Ignore optional tests.
      #~(list "--ignore=docs_src"
              "--ignore=tests/test_tutorial"
              ;; Unclear why this test fails.
              "-k" "not test_select_gen")))
    (propagated-inputs
     (list python-pydantic
           python-sqlalchemy-2
           python-typing-extensions))
    (native-inputs
     (list python-pdm-backend
           python-dirty-equals
           python-pytest))
    (home-page "https://github.com/fastapi/sqlmodel")
    (synopsis "SQLModel, SQL databases in Python, designed")
    (description
     "SQLModel is a library for interacting with SQL databases from
Python code, with Python objects.  It is based on Python type
annotations, and powered by Pydantic and SQLAlchemy.")
    (license license:expat)))

(define-public python-udocker
  (package
    (name "python-udocker")
    (version "1.3.17")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
              (url "https://github.com/indigo-dc/udocker")
              (commit version)))
       (file-name (git-file-name name version))
       (sha256
        (base32 "1nbsj3kwlnkr12ykl1xd0r2hykikhrs0z9wgfb26y2nxpf85z3rz"))))
    (build-system pyproject-build-system)
    ;; Daemon chroot inconsistencies.
    (arguments (list #:test-flags #~(list "-k" "not test_05__get_volume_bindings")))
    (native-inputs (list python-pytest python-setuptools))
    (home-page "https://github.com/indigo-dc/udocker")
    (synopsis "Execute simple docker containers without root privileges")
    (description
     "This package provides a basic user tool to execute simple docker containers in
batch or interactive systems without root privileges.")
    (license license:asl2.0)))

(define-public python-snakemake-interface-common
  (package/inherit guix:python-snakemake-interface-common
    (name "python-snakemake-interface-common")
    (properties '((commit . "d585b5c0c7c0ec0df60a1a26d5d413f3ee88e63f")
                  (revision . "0")))
    (version (git-version "1.23.0"
                          (assoc-ref properties 'revision)
                          (assoc-ref properties 'commit)))
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
              (url "https://github.com/snakemake/snakemake-interface-common")
              (commit (assoc-ref properties 'commit))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "1zxks3jjwc5addx5wxgfb5zn2y2jzxz53n739b9w8qba3nwnzyj2"))
       (patches
        (snakemake-guix-patches "python-snakemake-interface-common-allow-missing.patch"))))
    (build-system pyproject-build-system)
    (propagated-inputs
     (list python-argparse-dataclass
           python-configargparse
           python-packaging))
    (native-inputs
     (list python-pytest
           python-setuptools))))

(define-public python-snakemake-interface-executor-plugins
  (package/inherit guix:python-snakemake-interface-executor-plugins
    (name "python-snakemake-interface-executor-plugins")
    (version "9.4.0")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
              (url (string-append "https://github.com/snakemake/"
                                  "snakemake-interface-executor-plugins"))
              (commit (string-append "v" version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "1qz4cl5wyinhk191ivkxn0ghjjdicyvg6wq97b1bgn01qqfdvxkq"))))
    (arguments
     (list
      #:test-backend #~'custom
      #:test-flags #~(list "tests/tests.py")))
    (propagated-inputs (list python-snakemake-interface-common))))

(define-public python-snakemake-interface-logger-plugins
  (package
    (name "python-snakemake-interface-logger-plugins")
    (version "2.0.1")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
              (url (string-append "https://github.com/snakemake/"
                                  "snakemake-interface-logger-plugins"))
              (commit (string-append "v" version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "138z6i810v374h27gj9jxg5jwdz6ccyirgv2f2l313j1iivj7wfa"))))
    (build-system pyproject-build-system)
    (arguments
     (list
      #:test-flags #~(list "tests/tests.py")))
    (propagated-inputs (list python-snakemake-interface-common))
    (native-inputs
     (list python-hatchling
           python-snakemake-logger-plugin-rich
           python-pytest))
    (home-page (string-append "https://github.com/snakemake/"
                              "python-snakemake-interface-logger-plugins"))
    (synopsis "Interface for Snakemake logger plugins")
    (description
     "This package provides a stable interface for interactions between Snakemake and
its logger plugins.")
    (license license:expat)))

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

(define-public python-snakemake-interface-scheduler-plugins
  (package
    (name "python-snakemake-interface-scheduler-plugins")
    (version "2.0.2")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
              (url (string-append "https://github.com/snakemake/"
                                  "snakemake-interface-scheduler-plugins"))
              (commit (string-append "v" version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "0bz33dl90cblzs9gki8kmklv9zkdh22883455541y5b5k70hr306"))))
    (build-system pyproject-build-system)
    (arguments
     (list
      ;; XXX: Tests collect but snakemake.scheduler is missing.
      #:tests? #f
      #:test-flags #~(list "tests/tests.py")))
    (propagated-inputs (list python-snakemake-interface-common))
    (native-inputs
     (list python-hatchling
           python-pytest
           guix:snakemake))
    (home-page (string-append "https://github.com/snakemake/"
                              "python-snakemake-interface-scheduler-plugins"))
    (synopsis "Interface for Snakemake scheduler plugins")
    (description
     "This package provides a stable interface for interactions between Snakemake and
its scheduler plugins.")
    (license license:expat)))

(define-public python-tenacity-9.1
  (package/inherit python-tenacity
    (version "9.1.4")
    (source
     (origin
       (method url-fetch)
       (uri (pypi-uri "tenacity" version))
       (sha256
        (base32 "0fprkhbrh26zm9jxpwmcz5vpr989hd4kpcqs110x0arz4r61vcxd"))))))

(define-public python-snakemake-interface-storage-plugins
  (package/inherit guix:python-snakemake-interface-storage-plugins
    (name "python-snakemake-interface-storage-plugins")
    (version "4.4.1")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
              (url (string-append "https://github.com/snakemake/"
                                  "snakemake-interface-storage-plugins"))
             (commit (string-append "v" version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "0nv6zldqspjvy27g94rz4cpnk34jrh6gyfb2zkqk7y1mflk8i95n"))))
    (propagated-inputs
     (list python-humanfriendly
           python-snakemake-interface-common
           python-tenacity-9.1
           python-throttler
           python-wrapt))))

(define-public python-snakemake-interface-software-deployment-plugins
  (package/inherit guix:python-snakemake-interface-software-deployment-plugins
    (name "python-snakemake-interface-software-deployment-plugins")
    (version "0.18.6")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
              (url (string-append "https://github.com/snakemake/"
                                  "snakemake-interface-software-deployment-plugins"))
              (commit (string-append "v" version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "10dv8317ryxa05bdfyy6hqlwjxl0crnhfy66zvsl662zvzcb2hm6"))))
    (build-system pyproject-build-system)
    (arguments
     (list
      #:test-flags #~(list "--ignore=tests/test_py37.py")))
    (propagated-inputs (list python-argparse-dataclass
                             python-snakemake-interface-common))
    (native-inputs
     (list python-hatchling
           python-pytest
           python-snakemake-software-deployment-plugin-envmodules-bootstrap))))

(define-public python-snakemake-logger-plugin-rich
  (package
    (name "python-snakemake-logger-plugin-rich")
    (version "0.4.1")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
              (url "https://github.com/cademirch/snakemake-logger-plugin-rich")
              (commit (string-append "v" version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "07r2gqhxqs5ijqh4yjrdcwj60aqr66iglm6jvdwkgr9x0dmg7j4h"))))
    (build-system pyproject-build-system)
    (arguments
     (list
      ;; XXX: --logger argument is not recognized.
      #:tests? #f))
    (propagated-inputs
     (list python-pydantic
           python-rich
           python-snakemake-interface-executor-plugins
           (package/inherit python-snakemake-interface-logger-plugins
             (name "python-snakemake-interface-logger-plugins-bootstrap")
             (arguments (list #:tests? #f))
             (native-inputs (list python-hatchling)))))
    (native-inputs
     (list python-hatchling
           python-pytest
           guix:snakemake))
    (home-page "https://github.com/cademirch/snakemake-logger-plugin-rich")
    (synopsis "Log plugin for snakemake using Rich")
    (description "This package provides a logging plugin for Snakemake
that utilizes @code{python-rich} for enhanced terminal styling and
progress bars.")
    (license license:expat)))

(define-public python-snakemake-software-deployment-plugin-container
  (package
    (name "python-snakemake-software-deployment-plugin-container")
    (version "0.6.2")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
              (url (string-append "https://github.com/snakemake/"
                                  "snakemake-software-deployment-plugin-container"))
              (commit (string-append "v" version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "0izkmnr89cfd085z99bp4yf57djppb462n6k04fhi2k5mk93mzlm"))))
    (build-system pyproject-build-system)
    (arguments
     (list
      ;; Tests require network access.
      #:tests? #f))
    (propagated-inputs
     (list python-snakemake-interface-common
           python-snakemake-interface-software-deployment-plugins
           python-udocker))
    (native-inputs (list python-hatchling python-pytest))
    (home-page (string-append "https://github.com/snakemake/"
                              "snakemake-software-deployment-plugin-container"))
    (synopsis "Run Snakemake within a rootless container")
    (description "This package provides a generic container plugin
implementing snakemake's software-deployment interface.")
    (license license:expat)))

(define-public python-snakemake-software-deployment-plugin-envmodules
  (package
    (name "python-snakemake-software-deployment-plugin-envmodules")
    (version "0.2.0")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
              (url (string-append "https://github.com/snakemake/"
                                  "snakemake-software-deployment-plugin-envmodules"))
              (commit (string-append "v" version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "1764502r8vqg3k61wjc81rfi5v89rxj0njhpcfynxxx82rnda0vv"))))
    (build-system pyproject-build-system)
    (arguments
     (list
      #:test-backend #~'custom
      #:test-flags #~(list "tests/test_plugin.py")))
    (propagated-inputs
     (list python-snakemake-interface-common
           python-snakemake-interface-software-deployment-plugins))
    (native-inputs (list python-hatchling python-pytest))
    (home-page (string-append "https://github.com/snakemake/"
                              "snakemake-software-deployment-plugin-envmodules"))
    (synopsis "Environment modules plugin for Snakemake")
    (description
     "This package provides a software deployment plugin for Snakemake
using environment modules.")
    (license license:expat)))

(define-public python-snakemake-software-deployment-plugin-envmodules-bootstrap
  (package/inherit python-snakemake-software-deployment-plugin-envmodules
    (arguments
     (substitute-keyword-arguments
         (package-arguments python-snakemake-software-deployment-plugin-envmodules)
       ((#:tests? tests #t) #f)
       ((#:phases phases #~%standard-phases)
        #~(modify-phases #$phases
            (delete 'sanity-check)))))
    (propagated-inputs
     (modify-inputs
         (package-propagated-inputs python-snakemake-software-deployment-plugin-envmodules)
       (delete "python-snakemake-interface-software-deployment-plugins")))))

(define-public python-snakemake-storage-plugin-http
  (package
    (name "python-snakemake-storage-plugin-http")
    (version "0.3.1")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
              (url (string-append "https://github.com/snakemake/"
                                  "snakemake-storage-plugin-http"))
              (commit (string-append "v" version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "0mlc1nkz9l06ahz6s90lxrxvw5gz7krgyd7acyd51srv6lx0ipk9"))))
    (build-system pyproject-build-system)
    (arguments
     (list
      #:test-backend #~'custom
      #:test-flags #~(list "tests/tests.py")))
    (propagated-inputs
     (list python-requests
           python-requests-oauthlib
           python-snakemake-interface-common
           python-snakemake-interface-storage-plugins))
    (native-inputs (list python-poetry-core guix:snakemake))
    (home-page (string-append "https://github.com/snakemake/"
                              "snakemake-storage-plugin-http"))
    (synopsis "Download input files from HTTP(s) in Snakemake")
    (description
     "This package provides a storage plugin for downloading input
files from HTTP(s) in Snakemake.")
    (license license:expat)))

(define-public snakemake-with-software-deployment
  ;; Commit of branch feat/software-deployment-plugins
  (let ((commit "5d24c4d0316a9682e19865f0c9f919ba3cf26a60")
        (revision "1"))
    (package/inherit guix:snakemake
      (name "snakemake")
      ;; Version of last common commit with master branch
      (version (git-version "9.25.1" revision commit))
      (source
       (origin
         (method git-fetch)
         (uri (git-reference
                (url "https://github.com/snakemake/snakemake")
                (commit commit)))
         (file-name (git-file-name name version))
         (sha256
          (base32 "0lii85rk0l0apr9n8ymqz5mkk5082yp3hd02wvlb68jq4ak2arb2"))
         (patches
          (snakemake-guix-patches "snakemake-4009.patch"
                                  "snakemake-allow-without-conda.patch"
                                  "snakemake-record-software-structured.patch"))))
      (arguments
       (substitute-keyword-arguments (package-arguments guix:snakemake)
         ((#:test-flags test-flags)
          #~(cons*
             ;; Added, we ignore Conda
             ;; TODO Report upstream, this should not happen.
             "--ignore=tests/test_software_directive.py"
             ;; Broken
             "--ignore=tests/test_jupyter_notebook_pathlike.py"
             "--ignore=tests/test_persistence.py"
             "--deselect=tests/test_script.py::TestBashEncoder"
             "--deselect=tests/test_sourcecache.py::test_github_file_fetch"
             ;; This test requires snakemake-executor-plugin-cluster-generic.
             "--deselect=tests/test_logging.py::test_group_job_failure_events"
             #$test-flags))
         ((#:phases phases #~%standard-phases)
          #~(modify-phases #$phases
              (add-after 'unpack 'relax-requirements
                (lambda _
                  (substitute* "pyproject.toml"
                    (("\"pip\",")
                     "")
                    (("\"packaging.*\",")
                     "\"packaging\","))))
              (delete 'patch-version)
              (delete 'call-wrapper-not-wrapped-snakemake)))))
      (propagated-inputs
       (modify-inputs (package-propagated-inputs guix:snakemake)
         (replace "python-snakemake-interface-common"
           python-snakemake-interface-common)
         (replace "python-snakemake-interface-executor-plugins"
           python-snakemake-interface-executor-plugins)
         (replace "python-snakemake-interface-report-plugins"
           python-snakemake-interface-report-plugins)
         (replace "python-snakemake-interface-storage-plugins"
           python-snakemake-interface-storage-plugins)
         (replace "python-snakemake-interface-software-deployment-plugins"
           python-snakemake-interface-software-deployment-plugins)
         (append python-snakemake-interface-software-deployment-plugins
                 python-snakemake-interface-logger-plugins
                 python-snakemake-interface-scheduler-plugins
                 python-sqlmodel)))
      (native-inputs
       (modify-inputs (package-native-inputs guix:snakemake)
         (append python-pytest
                 python-setuptools-scm
                 python-snakemake-software-deployment-plugin-container
                 python-snakemake-software-deployment-plugin-envmodules))))))

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
           python-snakemake-interface-software-deployment-plugins))
    (home-page "https://github.com/nicolas-graves/snakemake-guix")
    (synopsis "Run Snakemake within a Guix shell or time-machine")
    (description "This package provides a software deployment plugin for Snakemake
using Guix command-line calls.")
    (license license:gpl3+)))

python-snakemake-software-deployment-plugin-guix
