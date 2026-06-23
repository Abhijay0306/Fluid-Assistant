import sys
import os

# Add project root to path so imports resolve correctly on Vercel
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mangum import Mangum
from main import app  # noqa: E402

handler = Mangum(app, lifespan="off")
