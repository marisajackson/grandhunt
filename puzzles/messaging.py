import logging
import requests
import traceback

from disco.api.client import APIClient
from disco.types.message import MessageEmbed

from django.utils import timezone
from django.conf import settings
from django.core.mail.message import EmailMultiAlternatives
from django.template.loader import render_to_string


logger = logging.getLogger('puzzles.messaging')


def dispatch_discord_alert(webhook, content, username='GPH Django'):
    content = '[{}] {}'.format(timezone.localtime().strftime('%H:%M:%S'), content)
    if len(content) >= 2000:
        content = content[:1996] + '...'
    if settings.IS_TEST:
        logger.info('Discord alert:\n' + content)
        return
    requests.post(webhook, data={'username': username, 'content': content})

def dispatch_general_alert(content, username='GPH AlertBot'):
    dispatch_discord_alert('FIXME', content, username)

def dispatch_submission_alert(content, username='GPH SubmissionBot'):
    dispatch_discord_alert('FIXME', content, username)

def dispatch_free_answer_alert(content, username='GPH HelpBot'):
    dispatch_discord_alert('FIXME', content, username)

def dispatch_victory_alert(content, username='GPH CongratBot'):
    dispatch_discord_alert('FIXME', content, username)


puzzle_logger = logging.getLogger('puzzles.puzzle')
def log_puzzle_info(puzzle, team, content):
    puzzle_logger.info('<{}> ({}) {}'.format(puzzle, team, content))

request_logger = logging.getLogger('puzzles.request')
def log_request_middleware(get_response):
    def middleware(request):
        request_logger.info('{} {}'.format(request.get_full_path(), request.user))
        return get_response(request)
    return middleware


def send_mail_wrapper(subject, template, context, recipients):
    if not recipients:
        return
    subject = settings.EMAIL_SUBJECT_PREFIX + subject
    body = render_to_string(template + '.txt', context)
    if settings.IS_TEST:
        logger.info('Sending mail <{}> to <{}>:\n{}'.format(
            subject, ', '.join(recipients), body))
        return
    mail = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email='FIXME',
        to=recipients,
        alternatives=[(render_to_string(template + '.html', context), 'text/html')],
        reply_to=['FIXME'])
    try:
        if mail.send() != 1:
            raise RuntimeError('Unknown failure???')
    except Exception:
        dispatch_general_alert('Could not send mail <{}> to <{}>:\n{}'.format(
            subject, ', '.join(recipients), traceback.format_exc()))


class EmptyEmbed:
    def to_dict(self):
        return {}

class DiscordInterface:
    TOKEN = None # FIXME
    GUILD = 'FIXME'
    HINT_CHANNEL = 'FIXME'

    def __init__(self):
        self.client = None
        self.avatars = {}
        if self.TOKEN and not settings.IS_TEST:
            self.client = APIClient(self.TOKEN)
            for member in self.client.guilds_members_list(self.GUILD).values():
                self.avatars[member.name] = member.user.avatar_url

    def update_hint(self, hint):
        if hint.claimed_datetime:
            embed = MessageEmbed()
            embed.color = 0xff0000
            embed.timestamp = hint.claimed_datetime.isoformat()
            embed.author.name = 'Claimed by {}'.format(hint.claimer)
            if hint.claimer in self.avatars:
                embed.author.icon_url = self.avatars[hint.claimer]
            debug = 'claimed by {}'.format(hint.claimer)
        else:
            embed = EmptyEmbed()
            debug = 'unclaimed'

        if hint.discord_id and self.client is not None:
            try:
                self.client.channels_messages_modify(
                    self.HINT_CHANNEL, hint.discord_id, embed=embed)
            except Exception:
                dispatch_general_alert('Discord API failure: modify\n{}'.format(
                    traceback.format_exc()))
        else:
            message = hint.discord_message()
            if self.client is None:
                logger.info('Hint, {}: {}\n{}'.format(debug, hint, message))
                return
            try:
                discord_id = self.client.channels_messages_create(
                    self.HINT_CHANNEL, message, embed=embed).id
            except Exception:
                dispatch_general_alert('Discord API failure: create\n{}'.format(
                    traceback.format_exc()))
                return
            hint.discord_id = discord_id
            hint.save(update_fields=('discord_id',))

    def clear_hint(self, hint):
        if self.client is None:
            logger.info('Hint done: {}'.format(hint))
            return
        if hint.discord_id:
            try:
                self.client.channels_messages_delete(
                    self.HINT_CHANNEL, hint.discord_id)
            except Exception:
                dispatch_general_alert('Discord API failure: delete\n{}'.format(
                    traceback.format_exc()))
            hint.discord_id = None
            hint.save(update_fields=('discord_id',))

discord_interface = DiscordInterface()
