import os


def launch_kwargs(**extra):
    """Common kwargs for chromium.launch().

    On systems where Playwright ships no bundled Chromium (e.g. ARM /
    Raspberry Pi), set PLAYWRIGHT_CHROMIUM_EXECUTABLE to the system browser
    (e.g. /usr/bin/chromium) and it will be used instead.
    """
    kwargs = {"headless": True}
    executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    if executable:
        kwargs["executable_path"] = executable
    kwargs.update(extra)
    return kwargs
