# Fix for missing imghdr module in Python 3.13
import sys
import mimetypes

if sys.version_info >= (3, 13):
    # Create fake imghdr module
    class ImghdrModule:
        def what(self, file):
            return mimetypes.guess_type(file)[0]
    
    sys.modules['imghdr'] = ImghdrModule()
