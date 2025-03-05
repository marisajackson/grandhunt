from .base import *

DEBUG = False

IS_TEST = False

# Used for constructing URLs; include the protocol and trailing
# slash (e.g. 'https://galacticpuzzlehunt.com/')
DOMAIN = 'https://2025.grandhuntdigital.com/'

# List of places you're serving from, e.g.
# ['galacticpuzzlehunt.com', 'gph.example.com']; or just ['*']
ALLOWED_HOSTS = ['2025.grandhuntdigital.com', 'grandhuntdigital.com', '127.0.0.1', '144.24.46.133']

# Google Analytics
GA_CODE = '''
<script>
  /* FIXME */
</script>
'''
