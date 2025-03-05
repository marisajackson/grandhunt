import datetime
from django.urls import reverse
from django.utils import timezone

# included in various templates. NOTE, sometimes appears with a "the" before
# it, maybe check those are what you want.
HUNT_TITLE = 'Grand Hunt 2025'
# included in various templates and displayed on the static site
HUNT_ORGANIZERS = 'The Agency'
# included in various templates and set as reply-to for automatic emails
CONTACT_EMAIL = 'info@thegrandhunt.com'
# the sender from which automatic emails are sent; your mail sending service
# might require you set this to something (check settings/base.py to put your
# actual mail sending service credentials)
MESSAGING_SENDER_EMAIL = 'noreply@grandhuntdigital.com'

# Change this to True to reveal the story page to everyone.
STORY_PAGE_VISIBLE = True
# Change this to True to reveal the meet the team page to everyone.
MEET_TEAM_PAGE_VISIBLE = True
# Change this to True when the wrapup exists.
WRAPUP_PAGE_VISIBLE = True
# Change this to True to start showing solve and guess counts on each puzzle.
# Full stats are automatically available to superusers and after hunt end.
INITIAL_STATS_AVAILABLE = False
# Change this to True to start showing post-solve surveys to teams.
# Survey results are only available to superusers.
SURVEYS_AVAILABLE = True

HUNT_START_TIME = timezone.make_aware(datetime.datetime(
    year=2025,
    month=1,
    day=9,
    hour=15,
    minute=0,
))
HUNT_END_TIME = timezone.make_aware(datetime.datetime(
    year=2025,
    month=1,
    day=20,
    hour=15,
    minute=0,
))
HUNT_CLOSE_TIME = timezone.make_aware(datetime.datetime(
    year=2025,
    month=1,
    day=20,
    hour=15,
    minute=0,
))

MAX_GUESSES_PER_PUZZLE = 20
MAX_MEMBERS_PER_TEAM = 6

# If this is disabled, teams will not get any hints.
HINTS_ENABLED = True
# Teams accumulate this many hints each day.
# Actually every 8 hours but I'm not renaming the variable
# Above comment was from 2023 hunt, and now it's changed to 12 hours per hint for 2024
HINTS_PER_DAY = (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1)
# Teams get the first number in HINTS_PER_DAY at this time, and subsequent
# numbers every day after until the end of HINTS_PER_DAY.
HINT_TIME = HUNT_START_TIME + datetime.timedelta(hours=0)
# To discourage teams from creating sockpuppets to grab more hints, teams
# created less than this time ago get nothing. Once the time elapses, they
# get the full number of hints, including retroactively.
# (We tried shifting the hint schedule back for teams depending on creation
# time, but it's hard to do fairly. Teams were confused about when and how
# many hints they would get, since we advertised that there would be intro
# hints or extra hints released at this or that time. Feel free to change the
# logic in models.py to suit your needs.)
TEAM_AGE_BEFORE_HINTS = datetime.timedelta(days=0)
# If set, a team's first N hints are usable only on puzzles in the intro round.
# (They don't go away or convert into regular hints after some time; if a team
# doesn't use them, they can still use regular hints they receive afterward.)
INTRO_HINTS = 0
# If this is enabled, a team may only have one open hint, and must wait for it
# to be answered before submitting another request.
ONE_HINT_AT_A_TIME = True

# These options are exactly analogous to the above.
FREE_ANSWERS_ENABLED = False
FREE_ANSWERS_PER_DAY = (1, 2, 2)
FREE_ANSWER_TIME = HUNT_START_TIME + datetime.timedelta(days=6)
TEAM_AGE_BEFORE_FREE_ANSWERS = datetime.timedelta(days=3)

# These two slugs are used in a couple places to determine teams' progress
# through the major milestones of the hunt (e.g. to determine how much story
# they can view) and to classify puzzles as intro-round or not. They won't make
# sense for every hunt.
INTRO_ROUND_SLUG = ''
META_META_SLUG = 'the-secret-blueprint'

# Used for unlocking the meta meta round after the first meta is solved
META_META_ROUND = 4

# Used for custom logic needed for the runaround puzzle
RUNAROUND_SLUG = 'the-blueprint'
