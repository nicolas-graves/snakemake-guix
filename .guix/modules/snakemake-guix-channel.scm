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
  #:use-module (gnu packages python-science))

(define-public snakemake-with-software-deployment
  (package/inherit snakemake
    (name "snakemake")
    (version "8.29.3")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
             (url "https://github.com/snakemake/snakemake")
             (commit (string-append "v" version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "15ng1saxvjazx46zxy6gl06m29w61qn470ids36ycikqckldb2sw"))
       (patches
        (list
         (origin
           (method url-fetch)
           (uri "https://patch-diff.githubusercontent.com/raw\
/snakemake/snakemake/pull/3339.patch")
           (sha256
            (base32
             "19qql7llf4v0hjz9kd49069rjmspqvvnygf5qy2vxhmrhxkmpim6")))))))
    (arguments
     (substitute-keyword-arguments (package-arguments snakemake)
       ((#:test-flags test-flags)
        #~(cons* "--ignore=tests/test_args.py"
                 "--ignore=tests/test_persistence.py"
                 #$test-flags))))
    (propagated-inputs
     (modify-inputs (package-propagated-inputs snakemake)
       (append python-snakemake-interface-software-deployment-plugins)))))

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
       (list snakemake-with-software-deployment
             python-snakemake-interface-software-deployment-plugins))
      (home-page "\
https://github.com/nicolas-graves/snakemake-deployment-plugin-guix")
      (synopsis "In development")
      (description "In development")
      (license license:gpl3+))))

python-snakemake-deployment-plugin-guix
