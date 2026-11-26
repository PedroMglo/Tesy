"""Original C270 monitor with only its ldd lookup bound to the explicit native environment."""

import sys

from linkage import child_ldd, run_bounded, search_from_args

if __name__ == "__main__":
    run_bounded.backend_library_hashes = child_ldd(search_from_args(sys.argv[1:]))
    raise SystemExit(run_bounded.main())
