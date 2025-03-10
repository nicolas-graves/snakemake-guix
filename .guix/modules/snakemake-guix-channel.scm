;; Copyright © 2025 Nicolas Graves <ngraves@ngraves.fr>

(define-module (snakemake-guix-channel)
  #:use-module (git)
  #:use-module (ice-9 match)
  #:use-module (ice-9 popen)
  #:use-module (ice-9 rdelim)
  #:use-module (guix build utils)
  #:use-module (guix build-system pyproject)
  #:use-module (guix build-system python)
  #:use-module (guix download)
  #:use-module (guix gexp)
  #:use-module (guix git-download)
  #:use-module ((guix licenses) #:prefix license:)
  #:use-module (guix memoization)
  #:use-module (guix packages)
  #:use-module (guix utils)
  #:use-module (gnu packages check)
  #:use-module (gnu packages package-management)
  #:use-module (gnu packages python)
  #:use-module (gnu packages python-build)
  #:use-module (gnu packages python-science)
  #:use-module (gnu packages python-web)
  #:use-module (gnu packages python-xyz)
  #:use-module (gnu packages version-control))

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
    (description
     "This package provides declarative CLIs with argparse and dataclasses.")
    (license license:expat)))

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
    (description "This package provides common functions and classes
for Snakemake and its plugins.")
    (license license:expat)))

(define-public python-snakemake-interface-executor-plugins
  (package
    (name "python-snakemake-interface-executor-plugins")
    (version "9.3.3")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
             (url "\
https://github.com/snakemake/snakemake-interface-executor-plugins")
             (commit (string-append "v" version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "1kjjcgkk1rbavb687x5ayw35ayhsnhpg9262k317x911wqpsj2fm"))))
    (build-system pyproject-build-system)
    (arguments
     (list #:phases
           #~(modify-phases %standard-phases
               (replace 'check
                 (lambda* (#:key tests? #:allow-other-keys)
                   (when tests?
                     (invoke "python3" "tests/tests.py")))))))
    (propagated-inputs (list python-argparse-dataclass
                             python-snakemake-interface-common
                             python-throttler))
    (native-inputs (list python-poetry-core python-pytest))
    (home-page "\
https://github.com/snakemake/python-snakemake-interface-executor-plugins")
    (synopsis "Interface for Snakemake executor plugins")
    (description
     "This package provides a stable interface for interactions between Snakemake and
its executor plugins.")
    (license license:expat)))

(define-public python-snakemake-interface-report-plugins
  (package
    (name "python-snakemake-interface-report-plugins")
    (version "1.1.0")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
             (url "\
https://github.com/snakemake/snakemake-interface-report-plugins")
             (commit (string-append "v" version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "0i6z9vk6nv2m3jsym0glrb7h9isdlfza2yq14vbqcslybdi9ykfa"))))
    (build-system pyproject-build-system)
    (arguments
     (list #:tests? #f  ;XXX: Circular dependency on snakemake
           #:phases
           #~(modify-phases %standard-phases
               (replace 'check
                 (lambda* (#:key tests? #:allow-other-keys)
                   (when tests?
                     (invoke "python3" "tests/tests.py")))))))
    (propagated-inputs (list python-snakemake-interface-common python-pytest))
    (native-inputs (list python-poetry-core))
    (home-page "\
https://github.com/snakemake/python-snakemake-interface-report-plugins")
    (synopsis "Interface for Snakemake report plugins")
    (description "The interface for Snakemake report plugins.")
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
    (home-page "\
https://github.com/snakemake/snakemake-interface-software-deployment-plugins")
    (synopsis "Interface for Snakemake software deployment plugins")
    (description
     "This package provides a stable interface for interactions between Snakemake and
its software deployment plugins.")
    (license license:expat)))

(define-public python-snakemake-interface-storage-plugins
  (package
    (name "python-snakemake-interface-storage-plugins")
    (version "3.3.0")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
             (url "\
https://github.com/snakemake/snakemake-interface-storage-plugins")
             (commit (string-append "v" version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "05n5xgwagb01nyzi8xfvp0nvdfl24lxidgksm7k86p68n1rijd5a"))))
    (build-system pyproject-build-system)
    (arguments
     (list #:tests? #f  ;XXX: Circular dependency on snakemake
           #:phases
           #~(modify-phases %standard-phases
               (replace 'check
                 (lambda* (#:key tests? #:allow-other-keys)
                   (when tests?
                     (invoke "python3" "tests/tests.py")))))))
    (propagated-inputs (list python-reretry python-snakemake-interface-common
                             python-throttler python-wrapt))
    (native-inputs (list python-poetry-core python-pytest))
    (home-page
     "https://github.com/snakemake/snakemake-interface-storage-plugins")
    (synopsis "Interface for Snakemake storage plugins")
    (description
     "This package provides a stable interface for interactions between
Snakemake and its storage plugins.")
    (license license:expat)))

(define-public python-throttler
  (package
    (name "python-throttler")
    (version "1.2.2")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
             (url "https://github.com/uburuntu/throttler")
             (commit (string-append "v" version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "1gn21x0zkm7rr7qijlz7nvw7z0mm1j2r0r2lslg7wln1z36gjkbw"))))
    (build-system pyproject-build-system)
    (native-inputs (list python-aiohttp
                         python-pytest
                         python-pytest-asyncio
                         python-pytest-cov
                         python-setuptools
                         python-wheel))
    (home-page "https://github.com/uburuntu/throttler")
    (synopsis "Throttling with asyncio support in Python")
    (description
     "This package provides a zero-dependency Python package for easy
throttling with asyncio support.")
    (license license:expat)))

(define-public python-reretry
  (package
    (name "python-reretry")
    (version "0.11.8")
    (source
     (origin
       (method url-fetch)
       (uri (pypi-uri "reretry" version))
       (sha256
        (base32 "1qrjsjzah8gw1bciqn8bhrj80fjjg13qg8jks7qs4bjipv71yygj"))))
    (build-system pyproject-build-system)
    (native-inputs (list python-setuptools python-wheel))
    (home-page "https://github.com/leshchenko1979/reretry")
    (synopsis "Python decorator for retrying on exceptions")
    (description
     "This provides an easy to use, but functional decorator for retrying on
exceptions.")
    (license license:asl2.0)))

(define-public python-conda-inject
  (package
    (name "python-conda-inject")
    (version "1.3.2")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
             (url "https://github.com/koesterlab/conda-inject")
             (commit (string-append "v" version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "1aig9l676wc2sjb20y7rdqf0hfcfjhh92yfiy82mf7kfnv7rp3rk"))))
    (build-system pyproject-build-system)
    (arguments
     (list #:phases
           #~(modify-phases %standard-phases
               (replace 'check
                 (lambda* (#:key tests? #:allow-other-keys)
                   (when tests?
                     (invoke "python3" "tests/tests.py")))))))
    (propagated-inputs (list python-pyyaml))
    (native-inputs (list python-poetry-core python-pytest))
    (home-page "https://github.com/koesterlab/conda-inject")
    (synopsis
     "Inject a conda environment into the current python environment")
    (description
     "This package provides helper functions for injecting a conda
environment into the current python environment (by modifying @code{sys.path},
without actually changing the current python environment).")
    (license license:expat)))

(define-public snakemake-8
  (package
    (name "python-snakemake")
    (version "8.29.2")
    (source
     (origin
       (method url-fetch)
       (uri (pypi-uri "snakemake" version))
       (sha256
        (base32 "1ilpmrjmnc529p4gw2x23ik1d8b5pm6k1dhq08dknvfjsf3vgyjr"))))
    (build-system pyproject-build-system)
    (arguments
     (list
      #:test-flags
      '(list
        ;; XXX: Unclear why these tests fail.
        "--ignore=tests/test_report_href/test_script.py"
        "--ignore=tests/test_script_py/scripts/test_explicit_import.py"
        "--ignore=tests/test_output_index.py"
        ;; We don't care about testing old python@3.7 on Guix.
        "--ignore=tests/test_conda_python_3_7_script/test_script.py"
        ;; Those require additional snakemake plugins.
        "--ignore=tests/test_api.py"
        "--ignore=tests/test_executor_test_suite.py"
        ;; We don't care about lints.
        "--ignore=tests/test_linting.py"
        ;; These tests attempt to change S3 buckets on AWS and fail
        ;; because there are no AWS credentials.
        "--ignore=tests/test_tibanna"
        ;; It's a similar story with this test, which requires access
        ;; to the Google Storage service.
        "--ignore=tests/test_google_lifesciences")
      #:phases
      #~(modify-phases %standard-phases
          (add-after 'unpack 'avoid-assets-download
            (lambda _
              (substitute* "setup.py"
                (("^from assets import Assets") "")
                (("^Assets\\.deploy\\(\\)") ""))))
          ;; For cluster execution Snakemake will call Python.  Since there is
          ;; no suitable GUIX_PYTHONPATH set, cluster execution will fail.  We
          ;; fix this by calling the snakemake wrapper instead.
          (add-after 'unpack 'call-wrapper-not-wrapped-snakemake
            (lambda _
              (substitute* "snakemake/executors/__init__.py"
                (("self\\.get_python_executable\\(\\),")
                 "")
                (("\"-m snakemake\"")
                 (string-append "\"" #$output
                                "/bin/snakemake" "\""))
                ;; The snakemake command produced by format_job_exec contains
                ;; references to /gnu/store.  Prior to patching above that's
                ;; just a reference to Python; after patching it's a reference
                ;; to the snakemake executable.
                ;;
                ;; In Tibanna execution mode Snakemake arranges for a certain
                ;; Docker image to be deployed to AWS.  It then passes its own
                ;; command line to Tibanna.  This is misguided because it only
                ;; ever works if the local Snakemake command was run inside
                ;; the same Docker image.  In the case of using Guix this is
                ;; never correct, so we need to replace the store reference.
                (("tibanna_args.command = command")
                 (string-append
                  "tibanna_args.command = command.replace('"
                  #$output "/bin/snakemake', 'python3 -m snakemake')")))))
          ;; No longer needed with 7.15.2+
          (add-after 'unpack 'tabulate-compatibility
            (lambda _
              (substitute* "snakemake/dag.py"
                (("\"job\": rule,")
                 "\"job\": rule.name,"))))
          (add-after 'unpack 'patch-version
            (lambda _
              (substitute* "setup.py"
                (("version=versioneer.get_version\\(\\)")
                 (format #f "version=~s" #$version)))
              (substitute* '("snakemake/_version.py"
                             "versioneer.py")
                (("0\\+unknown") #$version))))
          (add-before 'check 'pre-check
            (lambda* (#:key tests?  #:allow-other-keys)
              (when tests?
                (setenv "HOME" "/tmp")))))))
    (inputs
     (list python-appdirs
           python-conda-inject
           python-configargparse
           python-connection-pool
           python-docutils
           python-dpath
           python-gitpython
           python-humanfriendly
           python-immutables
           python-jinja2
           python-jsonschema
           python-nbformat
           python-packaging
           python-psutil
           python-pulp
           python-pyyaml
           python-requests
           python-reretry
           python-smart-open
           python-snakemake-interface-common
           python-snakemake-interface-executor-plugins
           python-snakemake-interface-report-plugins
           python-snakemake-interface-storage-plugins
           python-tabulate
           python-throttler
           python-wrapt
           python-yte))
    (native-inputs
     (list python-numpy
           python-pandas
           python-setuptools
           python-tomli
           python-wheel))
    (home-page "https://snakemake.github.io/")
    (synopsis
     "Workflow management system to create reproducible and scalable data analyses")
    (description
     "Workflow management system to create reproducible and scalable data analyses.")
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
      (native-inputs (list guix python-flit-core python-pytest))
      (propagated-inputs
       (list snakemake-8
             python-snakemake-interface-software-deployment-plugins))
      (home-page "\
https://github.com/nicolas-graves/snakemake-deployment-plugin-guix")
      (synopsis "In development")
      (description "In development")
      (license license:gpl3+))))

python-snakemake-deployment-plugin-guix
