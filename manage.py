#!/usr/bin/env python
import os, sys

#Coverage.py runs this in a way where our .pth file doesn't add this path.
if '/Users/trey/Work/cmg/hp3/thirdparty' not in sys.path:
    sys.path.append('/Users/trey/Work/cmg/hp3/thirdparty')

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings.common")

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
