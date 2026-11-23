#!/usr/bin/env python3
"""Analyze the C121 new-identity screen with the shared strict analyzer."""

import c121_nominal_server as campaign
import c120_analyze as analysis

analysis.ORDER = campaign.campaign.ORDER


if __name__ == "__main__":
    analysis.main()
