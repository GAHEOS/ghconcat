#!/usr/bin/env python3
"""
ghconcat – hierarchical, language-agnostic concatenation & templating tool.

Gaheos – https://gaheos.com
Copyright (c) 2025 GAHEOS S.A.
Copyright (c) 2025 Leonardo Gavidia Guerra <leo@gaheos.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

# SPDX-FileCopyrightText: 2025 GAHEOS S.A.
# SPDX-FileCopyrightText: 2025 Leonardo Gavidia Guerra
# SPDX-License-Identifier: AGPL-3.0-or-later

import logging
import os
import sys
from typing import NoReturn

from ghconcat import GhConcat  # API pública


def main() -> NoReturn:
    logger = logging.getLogger("ghconcat")
    try:
        GhConcat.run(sys.argv[1:])
        raise SystemExit(0)
    except KeyboardInterrupt:
        logger.error("Interrupted by user.")
        raise SystemExit(130)
    except BrokenPipeError:
        raise SystemExit(0)
    except Exception as exc:  # noqa: BLE001
        if os.getenv("DEBUG") == "1":
            raise
        logger.error("Unexpected error: %s", exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
