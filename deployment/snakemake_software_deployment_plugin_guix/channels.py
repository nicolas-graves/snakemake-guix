import re
from urllib.parse import urlsplit

from snakemake_interface_common.exceptions import WorkflowError

_SWHID_RE = re.compile(r"^swh:\d+:(cnt|dir|rev|rel|snp):[0-9a-f]{40}(;.*)?$")
_DIRECT_SCHEMES = {"http", "https"}


def is_swhid(value: str) -> bool:
    return bool(_SWHID_RE.match(value))


def classify_channels_value(value: str) -> str:
    """Classify a channels= value as "local" (a file path, subject to
    Snakemake's normal source-path rewriting/caching) or "direct" (a URI or
    SWHID passed straight to `guix time-machine -C`, since guix resolves
    these itself -- Snakemake's source cache has no `swh:` handler and would
    otherwise double-fetch http(s) URLs). Raises WorkflowError for schemes
    guix's -C does not accept.
    """
    if is_swhid(value):
        return "direct"
    scheme = urlsplit(value).scheme
    # A bare path (no scheme) is local. A single-letter "scheme" is a Windows
    # drive letter, not a URI scheme -- but this plugin is Guix/Linux-only,
    # so that case can't arise in practice.
    if not scheme:
        return "local"
    if scheme in _DIRECT_SCHEMES:
        return "direct"
    raise WorkflowError(
        f"guix software deployment: unsupported channels= scheme {scheme!r} "
        f"in {value!r}. Use a local file path (no 'file://' prefix), an "
        "http(s) URL, or a Software Heritage SWHID (e.g. "
        "swh:1:cnt:<40-hex-chars>)."
    )
