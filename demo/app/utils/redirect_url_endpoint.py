from flask import redirect, request, url_for
from urllib.parse import urlparse

def url_destination(fallback):
    """
    Redirect safely to ?next= if provided,
    otherwise redirect to fallback endpoint.
    """

    next_url = request.args.get("next")

    if not next_url:
        return redirect(fallback)

    # Prevent open redirects (security)
    parsed = urlparse(next_url)

    # Only allow relative URLs (same site)
    if parsed.netloc != "":
        return redirect(fallback)

    return redirect(next_url)