#!/usr/bin/env python3
"""New attempt identity after C120's premodel measurement-SHA failure."""

import c120_nominal_server as campaign

campaign.ORDER = (("c121-p1-control", "control", 1),
                  ("c121-p1-candidate", "candidate", 1),
                  ("c121-p2-candidate", "candidate", 2),
                  ("c121-p2-control", "control", 2))
campaign.ROOT_NAME = "c121-nominal153-20260929T1350Z"
campaign.CAMPAIGN_WRAPPER_FILE = __file__


if __name__ == "__main__":
    campaign.main()
