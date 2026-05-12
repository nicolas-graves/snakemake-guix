;; Copyright © 2025 Nicolas Graves <ngraves@ngraves.fr>

(define-module (snakemake-guix-channel)
  #:use-module (git)
  #:use-module (guix build-system pyproject)
  #:use-module (guix build-system python)
  #:use-module (guix download)
  #:use-module (guix gexp)
  #:use-module (guix git-download)
  #:use-module ((guix licenses) #:prefix license:)
  #:use-module (guix packages)
  #:use-module ((guix utils) #:select (substitute-keyword-arguments))
  #:use-module (gnu packages check)
  #:use-module (gnu packages package-management)
  #:use-module (gnu packages python)
  #:use-module (gnu packages python-build)
  #:use-module ((gnu packages python-science)
                #:select (snakemake
                          (python-snakemake-interface-common . python-snakemake-interface-common*)
                          (python-snakemake-interface-executor-plugins . python-snakemake-interface-executor-plugins*)
                          (python-snakemake-interface-report-plugins . python-snakemake-interface-report-plugins*)
                          (python-snakemake-interface-software-deployment-plugins . python-snakemake-interface-software-deployment-plugins*)
                          (python-snakemake-interface-storage-plugins . python-snakemake-interface-storage-plugins*)))
  #:use-module (gnu packages python-web)
  #:use-module (gnu packages python-xyz))

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
    (synopsis "Execute simple docker containers in batch or interactive systems without root privileges")
    (description
     "This package provides a basic user tool to execute simple docker containers in
batch or interactive systems without root privileges.")
    (license #f)))

(define-public python-snakemake-interface-common
  (package/inherit python-snakemake-interface-common*
    (name "python-snakemake-interface-common")
    (version "1.23.0")
    (source
     (origin
       (method url-fetch)
       (uri (pypi-uri "snakemake_interface_common" version))
       (sha256
        (base32 "1k7smzydkwqgw32mrhbgwbs6ly0vqnnd03aa6rcpchb1lhqlblbf"))))
    (build-system pyproject-build-system)
    (propagated-inputs
     (list python-argparse-dataclass
           python-configargparse
           python-packaging))
    (native-inputs
     (list python-pytest
           python-setuptools))))

(define-public python-snakemake-interface-executor-plugins
  (package/inherit python-snakemake-interface-executor-plugins*
    (name "python-snakemake-interface-executor-plugins")
    (version "9.4.0")
    (source
     (origin
       (method url-fetch)
       (uri (pypi-uri "snakemake_interface_executor_plugins" version))
       (sha256
        (base32 "0rn0ya8g0mxccp7zjy7wnw2bdblfjhzvd55dxpdamjzagf4khhcx"))))
    (arguments '(#:tests? #f))
    (propagated-inputs (list python-snakemake-interface-common))))

(define-public python-snakemake-interface-logger-plugins
  (package
    (name "python-snakemake-interface-logger-plugins")
    (version "2.0.1")
    (source
     (origin
       (method url-fetch)
       (uri (pypi-uri "snakemake_interface_logger_plugins" version))
       (sha256
        (base32 "1q9hnkqgn620y1vqgzy69m77pc91xxcxr3jx4m93v68q7imwqffn"))))
    (build-system pyproject-build-system)
    (propagated-inputs (list python-snakemake-interface-common))
    (native-inputs (list python-hatchling))
    (home-page #f)
    (synopsis "Logger plugin interface for snakemake")
    (description "Logger plugin interface for snakemake.")
    (license #f)))

(define-public python-snakemake-interface-report-plugins
  (package/inherit python-snakemake-interface-report-plugins*
    (name "python-snakemake-interface-report-plugins")
    (version "2.0.1")
    (source
     (origin
       (method url-fetch)
       (uri (pypi-uri "snakemake_interface_report_plugins" version))
       (sha256
        (base32 "1y7y1ca484spryn4b8dfk38645vfrrq5vy41ikgghc4s4j6vich5"))))
    (propagated-inputs (list python-snakemake-interface-common))))

(define-public python-snakemake-interface-scheduler-plugins
  (package
    (name "python-snakemake-interface-scheduler-plugins")
    (version "2.0.2")
    (source
     (origin
       (method url-fetch)
       (uri (pypi-uri "snakemake_interface_scheduler_plugins" version))
       (sha256
        (base32 "0incr9qhlx5lhjwnd2ld9jnwblzwsqa3yh1b5h9q7n8rj3xfi5r7"))))
    (build-system pyproject-build-system)
    (propagated-inputs (list python-snakemake-interface-common))
    (native-inputs (list python-hatchling))
    (home-page #f)
    (synopsis "Scheduler plugin interface for snakemake")
    (description "Scheduler plugin interface for snakemake.")
    (license #f)))

(define-public python-snakemake-interface-storage-plugins
  (package/inherit python-snakemake-interface-storage-plugins*
    (name "python-snakemake-interface-storage-plugins")
    (version "4.4.1")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
             (url
              "https://github.com/snakemake/snakemake-interface-storage-plugins")
             (commit (string-append "v" version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "0nv6zldqspjvy27g94rz4cpnk34jrh6gyfb2zkqk7y1mflk8i95n"))))
    (propagated-inputs
     (list python-humanfriendly
           python-snakemake-interface-common
           python-tenacity
           python-throttler
           python-wrapt))))

(define-public python-snakemake-interface-software-deployment-plugins
  (package/inherit python-snakemake-interface-software-deployment-plugins*
    (name "python-snakemake-interface-software-deployment-plugins")
    (version "0.17.0")
    (source
     (origin
       (method url-fetch)
       (uri (pypi-uri "snakemake_interface_software_deployment_plugins"
                      version))
       (sha256
        (base32 "0jgkmz4224vg8msdl8rf9yzz8sc20s685pzfzhxvakhiaasdqznc"))))
    (build-system pyproject-build-system)
    (arguments
     (list
      #:test-flags
      #~(list
         ;; For a specific version of Python.
         "--ignore=tests/test_py37.py")))
    (propagated-inputs (list python-argparse-dataclass
                             python-snakemake-interface-common))
    (native-inputs
     (list python-hatchling
           python-pytest
           python-snakemake-software-deployment-plugin-envmodules-bootstrap))))

(define-public python-snakemake-software-deployment-plugin-conda
  (package
    (name "python-snakemake-software-deployment-plugin-conda")
    (version "0.5.0")
    (source
     (origin
       (method url-fetch)
       (uri (pypi-uri "snakemake_software_deployment_plugin_conda" version))
       (sha256
        (base32 "0apbp77fxm18alw5fxvbq8dwj454pmsdmapyyl0l5mwsdsj070p0"))))
    (build-system pyproject-build-system)
    (arguments
     (list
      #:phases
      #~(modify-phases %standard-phases
          (delete 'sanity-check))))
    (propagated-inputs
     (list python-aiofiles
           python-httpx
           ;; python-py-rattler
           python-pyyaml
           python-snakemake-interface-common
           python-snakemake-interface-software-deployment-plugins
           ;; XXX: Is python-uv that hard to inject in Guix?
           ;; python-uv
           ))
    (native-inputs (list python-hatchling))
    (home-page #f)
    (synopsis
     "Software deployment plugin for Snakemake using rattler to deploy conda packages.")
    (description
     "Software deployment plugin for Snakemake using rattler to deploy conda packages.")
    (license #f)))

(define-public python-snakemake-software-deployment-plugin-container
  (package
    (name "python-snakemake-software-deployment-plugin-container")
    (version "0.6.0")
    (source
     (origin
       (method url-fetch)
       (uri (pypi-uri "snakemake_software_deployment_plugin_container" version))
       (sha256
        (base32 "1mhnm2bw6315liwkksadfnjwzmal6ih13h24k3zq5qbqj00f1gbx"))))
    (build-system pyproject-build-system)
    (propagated-inputs
     (list python-snakemake-interface-common
           python-snakemake-interface-software-deployment-plugins
           python-udocker))
    (native-inputs (list python-hatchling))
    (home-page #f)
    (synopsis "")
    (description #f)
    (license #f)))

(define-public python-snakemake-software-deployment-plugin-envmodules
  (package
    (name "python-snakemake-software-deployment-plugin-envmodules")
    (version "0.2.0")
    (source
     (origin
       (method url-fetch)
       (uri (pypi-uri "snakemake_software_deployment_plugin_envmodules"
                      version))
       (sha256
        (base32 "1yc7dfksi4n7cjn0zfqdwwvhw4ak6061jnjy24vhb8q24r9a08z1"))))
    (build-system pyproject-build-system)
    (propagated-inputs
     (list python-snakemake-interface-common
           python-snakemake-interface-software-deployment-plugins))
    (native-inputs (list python-hatchling))
    (home-page #f)
    (synopsis
     "Software deployment plugin for Snakemake using environment modules.")
    (description
     "Software deployment plugin for Snakemake using environment modules.")
    (license #f)))

(define-public python-snakemake-software-deployment-plugin-envmodules-bootstrap
  (package/inherit python-snakemake-software-deployment-plugin-envmodules
    (arguments
     (substitute-keyword-arguments arguments
       ((#:phases phases #~%standard-phases)
        #~(modify-phases #$phases
            (delete 'sanity-check)))))
    (propagated-inputs
     (modify-inputs propagated-inputs
       (delete "python-snakemake-interface-software-deployment-plugins")))))

(define-public snakemake-with-software-deployment
  ;; Commit of branch feat/software-deployment-plugins
  (let ((commit "f2029839945cfe66eeef6fc3c1ddf779a76f58ce")
        (revision "0"))
    (package/inherit snakemake
      (name "snakemake")
      ;; Version of last common commit with master branch
      (version (git-version "9.17.0" revision commit))
      (source
       (origin
         (method git-fetch)
         (uri (git-reference
                (url "https://github.com/snakemake/snakemake")
                (commit commit)))
         (file-name (git-file-name name version))
         (sha256
          (base32 "11079q76kwm9kyvnri28n7f22zqv40zica50wwv1sm3n95avsqwr"))
         (patches
          (list (local-file (string-append (dirname (current-filename))
                                           "/4009.patch"))))))
      (arguments
       (substitute-keyword-arguments (package-arguments snakemake)
         ((#:tests? tests? #t) #f)
         ((#:test-flags test-flags)
          #~(cons* "--ignore=tests/test_args.py"
                   "--ignore=tests/test_persistence.py"
                   #$test-flags))
         ((#:phases phases #~%standard-phases)
          #~(modify-phases #$phases
              ;; Let that slide for now
              ;; Requirement.parse('uv<0.7.0,>=0.6.5'), {'snakemake-software-deployment-plugin-conda'}
              (delete 'sanity-check)
              (delete 'patch-version)
              (delete 'call-wrapper-not-wrapped-snakemake)))))
      (propagated-inputs
       (modify-inputs (package-propagated-inputs snakemake)
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
                 ;; TODO We should be able to make that optional...
                 python-snakemake-interface-logger-plugins
                 python-snakemake-interface-scheduler-plugins
                 python-snakemake-software-deployment-plugin-conda
                 python-snakemake-software-deployment-plugin-container
                 python-snakemake-software-deployment-plugin-envmodules)))
      (native-inputs
       (modify-inputs native-inputs
         (append python-pytest python-setuptools-scm))))))

(define-public python-snakemake-deployment-plugin-guix
  (let* ((source-dir (dirname (dirname (dirname (current-filename)))))
         (repo (repository-open source-dir))
         (commit (oid->string (object-id (revparse-single repo "HEAD")))))
    (package
      (name "python-snakemake-deployment-plugin-guix")
      (version (git-version "0.1.0" "0" commit))
      (source (local-file source-dir
                          #:recursive? #t
                          #:select? (git-predicate source-dir)))
      (build-system pyproject-build-system)
      (arguments
       (list #:test-flags #~(list "-k" "not test_deploy")))
      (native-inputs (list guix python-flit-core python-pytest))
      (propagated-inputs
       (list snakemake-with-software-deployment
             python-snakemake-interface-software-deployment-plugins))
      (home-page "\
https://github.com/nicolas-graves/snakemake-deployment-plugin-guix")
      (synopsis "In development")
      (description "In development")
      (license license:gpl3+))))

python-snakemake-deployment-plugin-guix
