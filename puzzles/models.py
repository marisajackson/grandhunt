import datetime
import re
from collections import defaultdict
from urllib.parse import quote_plus

from django import forms
from django.core.exceptions import ValidationError
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.db.models import F, FilteredRelation, Q, Case, When, Count, Min
from django.db.models.functions import Coalesce
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from puzzles.context import context_cache

from puzzles.messaging import (
    dispatch_general_alert,
    dispatch_free_answer_alert,
    dispatch_submission_alert,
    send_mail_wrapper,
    discord_interface,
)

from puzzles.hunt_config import (
    HUNT_START_TIME,
    HUNT_END_TIME,
    MAX_GUESSES_PER_PUZZLE,

    HINTS_ENABLED,
    HINTS_PER_DAY,
    DAYS_BEFORE_HINTS,
    TEAM_AGE_BEFORE_HINTS,
    CAP_HINTS_BY_TEAM_AGE,

    FREE_ANSWERS_ENABLED,
    DAYS_BEFORE_FREE_ANSWERS,
    CAP_FREE_ANSWERS_BY_TEAM_AGE,
    FREE_ANSWERS_PER_DAY,

    DEEP_MAX,
    INTRO_META_SLUG,
    META_META_SLUG,
)


class Puzzle(models.Model):
    '''A single puzzle in the puzzlehunt.'''

    name = models.CharField(max_length=500)

    # I considered making this default to django.utils.text.slugify(name) via
    # cleaning, but that's a bit more invasive because you need blank=True for
    # the admin page to let you submit blank strings, and there will be errors
    # if a blank slug sneaks past into your database (e.g. the puzzle page
    # can't be URL-reversed). Note that not all routes a model could enter the
    # database will call clean().
    slug = models.SlugField(
        max_length=500, unique=True,
        help_text='Slug used in URLs to identify this puzzle (must be unique)',
    )

    # As in the comment above, although we replace blank values with the
    # default in clean(), a blank body template could sneak in anyway, but it
    # seems less likely to be harmful here.
    body_template = models.CharField(
        max_length=500, blank=True,
        help_text='''File name of a Django template (including .html) under
        puzzle_bodies and solution_bodies containing the puzzle and
        solution content, respectively. Defaults to slug + ".html" if not
        specified.''',
    )

    answer = models.CharField(
        max_length=500,
        help_text='Answer (fine if unnormalized)',
    )

    deep = models.IntegerField(
        verbose_name='DEEP threshold',
        help_text='DEEP/Progress threshold teams must meet to unlock this puzzle'
    )

    # indicates if this puzzle is a metapuzzle
    is_meta = models.BooleanField(default=False)

    metas = models.ManyToManyField(
        'self', limit_choices_to={'is_meta': True}, symmetrical=False, blank=True,
        help_text='All metas that this puzzle is part of',
    )

    emoji = models.CharField(
        max_length=500, default=':question:',
        help_text='Emoji to use in Discord integrations involving this puzzle'
    )

    def clean(self):
        if not self.body_template:
            self.body_template = self.slug + '.html'

    def __str__(self):
        return self.name

    @property
    def short_name(self):
        ret = []
        last_alpha = False
        for c in self.name:
            if c.isalpha():
                if not last_alpha: ret.append(c)
                last_alpha = True
            elif c != "'":
                if c != ' ': ret.append(c)
                last_alpha = False
        if len(ret) >= 7:
            return ''.join(ret[:4]) + '...'
        else:
            return ''.join(ret)

    @property
    def normalized_answer(self):
        return Puzzle.normalize_answer(self.answer)

    @staticmethod
    def normalize_answer(s):
        return s and re.sub(r'[^A-Z]', '', s.upper())

    def is_intro(self):
        '''Is this puzzle in the intro round?'''
        # FIXME: Not all hunts have an intro round.
        return any(meta.slug == INTRO_META_SLUG for meta in self.metas.all())

@context_cache
class Team(models.Model):
    '''
    A team participating in the puzzlehunt.

    This model has a one-to-one relationship to Users -- every User created
    through the register flow will have a "Team" created for them.
    '''

    # The associated User -- note that not all users necessarily have an
    # associated team.
    user = models.OneToOneField(User, on_delete=models.PROTECT)

    # Public team name for scoreboards and comms -- not necessarily the same as
    # the user's name from the User object
    team_name = models.CharField(
        max_length=100, unique=True,
        help_text='Public team name for scoreboards and communications',
    )

    # Time of creation of team
    creation_time = models.DateTimeField(auto_now_add=True)

    start_offset = models.DurationField(
        default=datetime.timedelta,
        help_text='''How much earlier this team should start, for early-testing
        teams; be careful with this!''',
    )

    total_hints_awarded = models.IntegerField(
        default=0,
        help_text='''Number of additional hints to award the team (on top of
        the default amount per day)''',
    )
    total_free_answers_awarded = models.IntegerField(
        default=0,
        help_text='''Number of additional free answers to award the team (on
        top of the default amount per day)''',
    )

    last_solve_time = models.DateTimeField(null=True, blank=True)

    is_prerelease_testsolver = models.BooleanField(
        default=False,
        help_text='''Whether this team is a prerelease testsolver. If true, the
        team will have access to puzzles before the hunt starts''',
    )

    is_hidden = models.BooleanField(
        default=False,
        help_text='''If a team is hidden, it will not be visible to the
        public''',
    )

    def __str__(self):
        return self.team_name

    def get_emails(self, with_names=False):
        return [
            ((member.email, str(member)) if with_names else member.email)
            for member in self.teammember_set.all() if member.email
        ]

    def puzzle_submissions(self, puzzle):
        return [
            submission for submission in self.submissions
            if submission.puzzle == puzzle
        ]

    def puzzle_answer(self, puzzle):
        return puzzle.answer if any(
            submission.is_correct
            for submission in self.puzzle_submissions(puzzle)
        ) else None

    def guesses_remaining(self, puzzle):
        wrong_guesses = sum(
            1 for submission in self.puzzle_submissions(puzzle)
            if not submission.is_correct
        )
        extra_guess_grant = ExtraGuessGrant.objects.filter(
            team=self,
            puzzle=puzzle
        ).first() # will be model or None
        extra_guesses = (extra_guess_grant.extra_guesses if
                extra_guess_grant else 0)
        return MAX_GUESSES_PER_PUZZLE + extra_guesses - wrong_guesses

    @staticmethod
    def leaderboard(current_team, hide_hidden=True):
        '''
        Returns a list of dictionaries with data of teams in the order they
        should appear on the leaderboard. Dictionaries have the following keys:
          - 'id'
          - 'user_id'
          - 'team_name'
          - 'total_solves': number of solves (before hunt end)
          - 'last_solve_or_creation_time': last non-free solve (before hunt
            end), or if none, team creation time
          - 'metameta_solve_time': time of finishing the hunt (if before hunt
            end)

        This depends on the viewing team for hidden teams.
        '''

        return Team.leaderboard_teams(current_team, hide_hidden).values(
            'id',
            'user_id',
            'team_name',
            'total_solves',
            'last_solve_or_creation_time',
            'metameta_solve_time',
        )

    @staticmethod
    def leaderboard_teams(current_team, division=None, hide_hidden=True):
        '''
        Returns a (lazy, not-yet-evaluated) QuerySet of teams, in the order
        they should appear on the leaderboard, with the following annotations:
          - 'total_solves': number of solves (before hunt end)
          - 'last_solve_or_creation_time': last non-free solve (before hunt
            end), or if none, team creation time
          - 'metameta_solve_time': time of finishing the hunt (if before hunt
            end)

        This depends on the viewing team for hidden teams.
        '''

        q = Q()
        # be careful, this is not "always true", I think it's "always true" if
        # &'d and "always false" if |'d

        if hide_hidden:
            # hide hidden teams (usually)
            q &= Q(is_hidden=False)
            if current_team:
                # ...but always show current team, regardless of hidden status
                q |= Q(id=current_team.id)

        all_teams = Team.objects.filter(q, creation_time__lt=HUNT_END_TIME)

        # https://docs.djangoproject.com/en/3.1/ref/models/querysets/#filteredrelation-objects
        # FilteredRelation does a LEFT OUTER JOIN with additional conditions in
        # the ON clause, so every team survives; the other stuff aggregates it
        all_teams = all_teams.annotate(
            scoring_submissions=FilteredRelation(
                'answersubmission',
                condition=Q(
                    answersubmission__used_free_answer=False,
                    answersubmission__is_correct=True,
                    answersubmission__submitted_datetime__lt=HUNT_END_TIME,
                )
            ),
            total_solves=Count('scoring_submissions'),
            metameta_solve_time=Min(Case(
                When(
                    scoring_submissions__puzzle__slug=META_META_SLUG,
                    then='scoring_submissions__submitted_datetime',
                )
                # else, null by default
            )),
            # Coalesce(things) = the first of things that isn't null
            last_solve_or_creation_time=Coalesce('last_solve_time', 'creation_time'),
        ).order_by(
            F('metameta_solve_time').asc(nulls_last=True),
            F('total_solves').desc(),
            F('last_solve_or_creation_time'),
        )

        return all_teams

        # Old joined-in-python implementation, with a different output format,
        # follows. I couldn't convince myself that pushing all the annotations
        # and sort into the database necessarily improved performance, but I
        # don't think it got significantly worse either, and the above version
        # feels like it enables future optimizations more effectively; for
        # example, I think the fact that computing the ranking on the team page
        # only needs values_list('id', flat=True) is pretty good. (On the
        # other hand, there are hunt formats where completing the sort in the
        # database is very difficult or even impossible due to a more
        # complicated scoring/ranking algorithm or one that uses information
        # not available in the database, like GPH 2018...)

        # total_solves = defaultdict(int)
        # meta_times = {}
        # for team_id, slug, time in AnswerSubmission.objects.filter(
        #     used_free_answer=False, is_correct=True, submitted_datetime__lt=HUNT_END_TIME
        # ).values_list('team__id', 'puzzle__slug', 'submitted_datetime'):
        #     total_solves[team_id] += 1
        #     if slug == META_META_SLUG:
        #         meta_times[team_id] = time

        # return sorted(
        #     [{
        #         'team_name': team.team_name,
        #         'is_current': team == current_team,
        #         'total_solves': total_solves[team.id],
        #         'last_solve_time': team.last_solve_time or team.creation_time,
        #         'metameta_solve_time': meta_times.get(team.id),
        #         'team': team,
        #     } for team in all_teams],
        #     key=lambda d: (
        #         d['metameta_solve_time'] or HUNT_END_TIME,
        #         -d['total_solves'],
        #         d['last_solve_time'],
        #     )
        # )

    def team(self):
        return self

    def team_created_after_hunt_start(self):
        return max(0, (self.creation_time - self.start_time).days)

    def num_hints_total(self):
        '''
        Compute the total number of hints (used + remaining) available to this team.
        '''
        if not HINTS_ENABLED: return 0

        now = min(self.now, HUNT_END_TIME)
        days_since_hunt_start = (now - self.start_time).days
        time_since_team_created = now - self.creation_time
        if TEAM_AGE_BEFORE_HINTS is not None and time_since_team_created < TEAM_AGE_BEFORE_HINTS:
            # No hints available for first X days of any team (to discourage
            # creating additional teams after the hunt has started to farm
            # hints)
            return 0

        # First hint accumulation is on day 3...
        days = days_since_hunt_start - DAYS_BEFORE_HINTS + 1
        # ...unless the team was created later than that.
        if CAP_HINTS_BY_TEAM_AGE:
            days = min(days, days_since_hunt_start - self.team_created_after_hunt_start)

        return max(0, days) * HINTS_PER_DAY + self.total_hints_awarded

    def num_hints_used(self):
        return self.hint_set.filter(status__in=(Hint.ANSWERED, Hint.NO_RESPONSE)).count()

    def num_hints_remaining(self):
        return self.num_hints_total - self.num_hints_used

    def num_awarded_hints_remaining(self):
        return self.total_hints_awarded - self.num_hints_used

    def num_free_answers_total(self):
        if not FREE_ANSWERS_ENABLED: return 0

        days_since_hunt_start = (self.now - self.start_time).days
        if CAP_FREE_ANSWERS_BY_TEAM_AGE and self.team_created_after_hunt_start >= DAYS_BEFORE_FREE_ANSWERS - 1:
            # No free answers at all for late-created teams.
            return 0
        return sum(
            h for (i, h) in enumerate(FREE_ANSWERS_PER_DAY)
            if days_since_hunt_start >= DAYS_BEFORE_FREE_ANSWERS + i
        ) + self.total_free_answers_awarded

    def num_free_answers_used(self):
        return sum(
            1 for submission in self.submissions
            if submission.used_free_answer
        )

    def num_free_answers_remaining(self):
        return self.num_free_answers_total - self.num_free_answers_used

    def submissions(self):
        return tuple(
            self.answersubmission_set
            .select_related('puzzle')
            .prefetch_related('puzzle__metas')
            .order_by('-submitted_datetime')
        )

    def solves(self):
        return {
            submission.puzzle_id: submission.puzzle
            for submission in self.submissions
            if submission.is_correct
        }

    def db_unlocks(self):
        return tuple(
            self.puzzleunlock_set
            .select_related('puzzle')
            .order_by('-unlock_datetime')
        )

    # DEEP (name taken from the 2015 Mystery Hunt) is a global measure of
    # progress through the hunt used to determine when teams unlock each
    # puzzle. Each puzzle is unlocked at a certain global DEEP value. Solving
    # puzzles grants each team DEEP, as does the passage of time.

    # Because each Galactic Puzzle Hunt has had very different and often
    # complicated unlocking mechanisms, we have just included a stripped-down
    # implementation that computes how many puzzles each team has solved (so
    # each puzzle is worth 1 DEEP). You may want to replace it with your own
    # implementation, maybe depending on time or additional fields of puzzles,
    # or just a completely different unlocking implementation. You may also
    # want to cache its computation. This will depend on your hunt design and
    # structure.

    # If you do replace it, make sure to replace the descriptions where it's
    # displayed.
    @staticmethod
    def compute_deep(context):
        if context.hunt_is_prereleased or context.hunt_is_closed:
            return DEEP_MAX
        if context.team is None:
            if context.hunt_is_over:
                return DEEP_MAX
            return 0
        return len(context.team.solves)

    # NOTE: This method creates unlocks with the current time; in other words,
    # time-based unlocks are not correctly backdated. This is because the DEEP
    # over time algorithm is nonlinear and unlocks are not important enough to
    # warrant calculating the inverse function. This method will be called the
    # next time a puzzle or the puzzles list is loaded, so solvers should not
    # be affected, but it may be worth keeping in mind if you're doing analysis.
    @staticmethod
    def compute_unlocks(context):
        team = context.team
        deep = context.deep
        unlocks = None
        if team and not team.is_prerelease_testsolver:
            unlocks = {unlock.puzzle_id for unlock in team.db_unlocks}
        out = {'puzzles': [], 'ids': set()}
        for puzzle in context.all_puzzles:
            if puzzle.deep > deep:
                break
            if deep != DEEP_MAX and unlocks is not None and puzzle.id not in unlocks:
                PuzzleUnlock(team=team, puzzle=puzzle).save()
            out['puzzles'].append({'puzzle': puzzle})
            out['ids'].add(puzzle.id)
        return out


@receiver(post_save, sender=Team)
def notify_on_team_creation(sender, instance, created, **kwargs):
    if created:
        dispatch_general_alert('Team created: {}'.format(instance.team_name))


class TeamMember(models.Model):
    '''A person on a team.'''

    team = models.ForeignKey(Team, on_delete=models.CASCADE)

    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True, verbose_name='Email (optional)')

    def __str__(self):
        return '%s (%s)' % (self.name, self.email) if self.email else self.name


@receiver(post_save, sender=TeamMember)
def notify_on_team_member_creation(sender, instance, created, **kwargs):
    if created:
        dispatch_general_alert('Team {} added member {} ({})'.format(
            instance.team, instance.name, instance.email))


class PuzzleUnlock(models.Model):
    '''Represents a team having access to a puzzle (and when that occurred).'''

    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    puzzle = models.ForeignKey(Puzzle, on_delete=models.CASCADE)

    unlock_datetime = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return '%s -> %s @ %s' % (
            self.team, self.puzzle, self.unlock_datetime
        )

    class Meta:
        unique_together = ('team', 'puzzle')


@receiver(post_save, sender=PuzzleUnlock)
def notify_on_meta_unlock(sender, instance, created, **kwargs):
    if created:
        if instance.puzzle.slug == INTRO_META_SLUG:
            send_mail_wrapper('Intro Meta', 'FIXME', {}, instance.team.get_emails())
        elif instance.puzzle.slug == META_META_SLUG:
            send_mail_wrapper('Meta Meta', 'FIXME', {}, instance.team.get_emails())


class AnswerSubmission(models.Model):
    '''Represents a team making a solve attempt on a puzzle (right or wrong).'''

    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    puzzle = models.ForeignKey(Puzzle, on_delete=models.CASCADE)

    submitted_answer = models.CharField(max_length=500)
    is_correct = models.BooleanField()
    submitted_datetime = models.DateTimeField(auto_now_add=True)
    used_free_answer = models.BooleanField()

    def __str__(self):
        return '%s -> %s: %s, %s' % (
            self.team, self.puzzle, self.submitted_answer,
            'correct' if self.is_correct else 'wrong'
        )

    class Meta:
        unique_together = ('team', 'puzzle', 'submitted_answer')


@receiver(post_save, sender=AnswerSubmission)
def notify_on_answer_submission(sender, instance, created, **kwargs):
    if created:
        now = timezone.localtime()
        def format_time_ago(timestamp):
            if not timestamp:
                return ''
            diff = now - timestamp
            parts = ['', '', '', '']
            if diff.days > 0:
                parts[0] = '%dd' % diff.days
            seconds = diff.seconds
            parts[3] = '%02ds' % (seconds % 60)
            minutes = seconds // 60
            if minutes:
                parts[2] = '%02dm' % (minutes % 60)
                hours = minutes // 60
                if hours:
                    parts[1] = '%dh' % hours
            return ' {} ago'.format(''.join(parts))
        hints = Hint.objects.filter(team=instance.team, puzzle=instance.puzzle)
        hint_line = ''
        if len(hints):
            hint_line = '\nHints:' + ','.join('%s (%s%s)' % (
                format_time_ago(hint.submitted_datetime),
                hint.status,
                format_time_ago(hint.answered_datetime),
            ) for hint in hints)
        if instance.used_free_answer:
            dispatch_free_answer_alert(
                ':question: {} Team {} used a free answer on {}!{}'.format(
                    instance.puzzle.emoji, instance.team, instance.puzzle, hint_line))
        else:
            sigil = ':x:'
            if instance.is_correct:
                sigil = {
                    1: ':first_place:', 2: ':second_place:', 3: ':third_place:'
                }.get(AnswerSubmission.objects.filter(
                    puzzle=instance.puzzle,
                    is_correct=True,
                    used_free_answer=False,
                ).count(), ':white_check_mark:')
            dispatch_submission_alert(
                '{} {} Team {} submitted `{}` for {}: {}{}'.format(
                    sigil, instance.puzzle.emoji, instance.team,
                    instance.submitted_answer, instance.puzzle,
                    'Correct!' if instance.is_correct else 'Incorrect!!',
                    hint_line,
                ),
                correct=instance.is_correct)
        if not instance.is_correct:
            return
        if instance.puzzle.slug == INTRO_META_SLUG:
            send_mail_wrapper('Intro Meta', 'FIXME', {}, instance.team.get_emails())

        obsoleted_hints = Hint.objects.filter(
            team=instance.team,
            puzzle=instance.puzzle,
            status=Hint.NO_RESPONSE,
        )
        # Do this instead of obsoleted_hints.update(status=Hint.OBSOLETE,
        # answered_datetime=now) to trigger post_save.
        for hint in obsoleted_hints:
            hint.status = Hint.OBSOLETE
            hint.answered_datetime = now
            hint.save()

class ExtraGuessGrant(models.Model):
    '''Extra guesses granted to a particular team.'''

    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    puzzle = models.ForeignKey(Puzzle, on_delete=models.CASCADE)

    extra_guesses = models.IntegerField()

    def __str__(self):
        return '%s has %d extra guesses for puzzle %s' % (
            self.team, self.extra_guesses, self.puzzle,
        )

    class Meta:
        unique_together = ('team', 'puzzle')


class PuzzleMessage(models.Model):
    '''A "keep going" message shown on submitting a specific wrong answer.'''

    puzzle = models.ForeignKey(Puzzle, on_delete=models.CASCADE)

    guess = models.CharField(max_length=500)
    response = models.TextField()

    def __str__(self):
        return '%s: %s' % (self.puzzle, self.guess)

    @property
    def semicleaned_guess(self):
        return PuzzleMessage.semiclean_guess(self.guess)

    @staticmethod
    def semiclean_guess(s):
        return s and re.sub(r'[^A-Z0-9]', '', s.upper())


class RatingField(models.PositiveSmallIntegerField):
    '''Represents a single numeric rating (either fun or difficulty) of a puzzle.'''
    def __init__(self, max_rating, adjective, **kwargs):
        self.max_rating = max_rating
        self.adjective = adjective
        super().__init__(**kwargs)

    def formfield(self, **kwargs):
        choices = [(i, i) for i in range(1, self.max_rating + 1)]
        return super().formfield(**{
            'min_value': 1,
            'max_value': self.max_rating,
            'widget': forms.RadioSelect(
                choices=choices,
                attrs={'adjective': self.adjective},
            ),
            **kwargs,
        })

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs['max_rating'] = self.max_rating
        kwargs['adjective'] = self.adjective
        return name, path, args, kwargs


class Survey(models.Model):
    '''A rating given by a team to a puzzle after solving it.'''

    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    puzzle = models.ForeignKey(Puzzle, on_delete=models.CASCADE)

    # NOTE: Due to some pretty dynamic queries, the names of rating fields
    # should be pretty unique! They definitely shouldn't overlap with the names
    # of any fields of Puzzle.
    fun = RatingField(6, 'fun')
    difficulty = RatingField(6, 'hard')
    comments = models.TextField(blank=True, verbose_name='Anything else:')

    def __str__(self):
        return '%s: %s' % (self.puzzle, self.team)

    class Meta:
        unique_together = ('team', 'puzzle')

    @classmethod
    def fields(cls):
        return [
            field for field in cls._meta.get_fields()
            if isinstance(field, RatingField)
        ]


class Hint(models.Model):
    '''A request for a hint.'''

    NO_RESPONSE = 'NR'
    ANSWERED = 'ANS'
    REFUNDED = 'REF'
    OBSOLETE = 'OBS'

    STATUSES = (
        (NO_RESPONSE, 'No response'),
        (ANSWERED, 'Answered'),

        # we can't answer for some reason, or think that the hint is too small
        (REFUNDED, 'Refunded'),

        # puzzle was solved while waiting for hint
        (OBSOLETE, 'Obsolete'),
    )

    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    puzzle = models.ForeignKey(Puzzle, on_delete=models.CASCADE)

    submitted_datetime = models.DateTimeField(auto_now_add=True)
    hint_question = models.TextField()
    notify_emails = models.CharField(default='none', max_length=255)

    claimed_datetime = models.DateTimeField(null=True)

    # Making these null=True, blank=False is painful and apparently not
    # idiomatic Django. For example, if set that way, the Django admin won't
    # let you save a model with blank values. Just check for the empty string
    # or falsiness when you're using them.
    claimer = models.CharField(blank=True, max_length=255)
    discord_id = models.CharField(blank=True, max_length=255)

    answered_datetime = models.DateTimeField(null=True)
    status = models.CharField(choices=STATUSES, default=NO_RESPONSE, max_length=3)
    response = models.TextField(blank=True)

    def __str__(self):
        def abbr(s):
            if len(s) > 50:
                return s[:50] + '...'
            return s
        o = '{}, {}: "{}"'.format(
            self.team.team_name,
            self.puzzle.name,
            abbr(self.hint_question),
        )
        if self.status != self.NO_RESPONSE:
            o = o + ' {}'.format(self.status)
        return o

    def recipients(self):
        if self.notify_emails == 'all':
            return self.team.get_emails()
        if self.notify_emails == 'none':
            return []
        return [self.notify_emails]

    def full_url(self, claim=False):
        url = settings.DOMAIN + 'hint/%s' % self.id
        if claim: url += '?claim=true'
        return url

    def short_discord_message(self, threshold=500):
        return (
            'Hint requested on {} {} by {}\n'
            '```{}```\n'
        ).format(
            self.puzzle.emoji, self.puzzle, self.team,
            self.hint_question[:threshold],
        )

    def long_discord_message(self):
        return self.short_discord_message(1500) + (
            '**Team:** {} ({})\n'
            '**Puzzle:** {} ({})\n'
        ).format(
            settings.DOMAIN + 'team/%s' % quote_plus(self.team.team_name, safe=''),
            settings.DOMAIN + 'admin/puzzles/hint/?team__id__exact=%s' % self.team_id,
            settings.DOMAIN + 'solution/' + self.puzzle.slug,
            settings.DOMAIN + 'admin/puzzles/hint/?puzzle__id__exact=%s' % self.puzzle_id,
        )


@receiver(post_save, sender=Hint)
def notify_on_hint_update(sender, instance, created, update_fields, **kwargs):
    # The .save() calls when updating certain Hint fields pass update_fields
    # to control which fields are written, which can be checked here. This is
    # to be safe and prevent overtriggering of these handlers, e.g. spamming
    # the team with more emails if an answered hint is somehow claimed again.
    if not update_fields:
        update_fields = ()
    if instance.status == Hint.NO_RESPONSE:
        if 'discord_id' not in update_fields:
            discord_interface.update_hint(instance)
    else:
        if 'discord_id' not in update_fields:
            discord_interface.clear_hint(instance)
        if 'response' in update_fields:
            send_mail_wrapper(
                'Hint answered for {}'.format(instance.puzzle),
                'hint_answered_email', {'hint': instance}, instance.recipients())
