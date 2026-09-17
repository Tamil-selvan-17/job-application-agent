import os
import sys
import site

backend_dir = os.path.abspath(os.path.dirname(__file__))
site_packages = os.path.expanduser(r"~\AppData\Roaming\Python\Python314\site-packages")

if os.path.exists(site_packages):
    site.addsitedir(site_packages)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import unittest

# Explicit imports after addsitedir
from tests.test_models import TestModels
from tests.test_services import TestServices
from tests.test_routers import TestRouters

if __name__ == "__main__":
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestModels))
    suite.addTest(unittest.makeSuite(TestServices))
    suite.addTest(unittest.makeSuite(TestRouters))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
