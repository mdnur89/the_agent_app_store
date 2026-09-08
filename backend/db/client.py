"""The single shared Prisma instance.

Nearly every module reaches the database through this one, which makes it the
right place to guarantee .env has been loaded: the standalone scripts
(test_db.py, check_msgs.py) have no startup hook of their own, and previously
depended on Prisma's incidental, cwd-relative dotenv load to find DATABASE_URL.
"""

import config  # noqa: F401  (imported first, for its import-time side effect)

from prisma import Prisma

# Initialize a global Prisma instance for asyncio usage
db = Prisma()
