import os, sys

# When files are at root level (not inside app/ subfolder)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the app factory directly from __init__.py at root
from __init__ import create_app

app = create_app()

if __name__ == "__main__":
    app.run()
