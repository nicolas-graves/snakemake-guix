;; XXX: because of the patches, we must build that file from ./modules
(use-modules (git)
             (guix gexp)
             (guix git-download)
             (guix packages)
             (snakemake-guix packages))

(let* ((source-dir (dirname (dirname (current-filename))))
       (repo (repository-open source-dir))
       (commit (oid->string (object-id (revparse-single repo "HEAD")))))
  (package/inherit python-snakemake-software-deployment-plugin-guix
    (version (git-version "0.2.0" "0" commit))
    (source (local-file source-dir
                        #:recursive? #t
                        #:select? (git-predicate source-dir)))))
