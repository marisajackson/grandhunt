# Generated by Django 2.2.6 on 2020-02-04 05:47

import datetime
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import puzzles.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Puzzle',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=500)),
                ('slug', models.SlugField(max_length=500, unique=True)),
                ('body_template', models.CharField(max_length=500)),
                ('answer', models.CharField(max_length=500)),
                ('deep', models.IntegerField(verbose_name='DEEP threshold')),
                ('is_meta', models.BooleanField(default=False)),
                ('emoji', models.CharField(default=':question:', max_length=500)),
                ('metas', models.ManyToManyField(blank=True, limit_choices_to={'is_meta': True}, to='puzzles.Puzzle')),
            ],
        ),
        migrations.CreateModel(
            name='Team',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('team_name', models.CharField(max_length=100, unique=True)),
                ('creation_time', models.DateTimeField(auto_now_add=True)),
                ('start_offset', models.DurationField(default=datetime.timedelta)),
                ('total_hints_awarded', models.IntegerField(default=0)),
                ('total_free_answers_awarded', models.IntegerField(default=0)),
                ('last_solve_time', models.DateTimeField(blank=True, null=True)),
                ('is_prerelease_testsolver', models.BooleanField(default=False)),
                ('is_hidden', models.BooleanField(default=False)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='TeamMember',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name='Email (optional)')),
                ('team', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='puzzles.Team')),
            ],
        ),
        migrations.CreateModel(
            name='PuzzleMessage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('guess', models.CharField(max_length=500)),
                ('response', models.TextField()),
                ('puzzle', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='puzzles.Puzzle')),
            ],
        ),
        migrations.CreateModel(
            name='Hint',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('submitted_datetime', models.DateTimeField(auto_now_add=True)),
                ('hint_question', models.TextField()),
                ('notify_emails', models.CharField(default='none', max_length=255)),
                ('claimed_datetime', models.DateTimeField(null=True)),
                ('claimer', models.CharField(max_length=255, null=True)),
                ('discord_id', models.CharField(max_length=255, null=True)),
                ('answered_datetime', models.DateTimeField(null=True)),
                ('status', models.CharField(choices=[('NR', 'No response'), ('ANS', 'Answered'), ('AMB', 'Ambiguous'), ('OBS', 'Obsolete')], default='NR', max_length=3)),
                ('response', models.TextField(null=True)),
                ('puzzle', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='puzzles.Puzzle')),
                ('team', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='puzzles.Team')),
            ],
        ),
        migrations.CreateModel(
            name='Survey',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fun', puzzles.models.RatingField(adjective='fun', max_rating=6)),
                ('difficulty', puzzles.models.RatingField(adjective='hard', max_rating=6)),
                ('comments', models.TextField(blank=True, verbose_name='Anything else:')),
                ('puzzle', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='puzzles.Puzzle')),
                ('team', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='puzzles.Team')),
            ],
            options={
                'unique_together': {('team', 'puzzle')},
            },
        ),
        migrations.CreateModel(
            name='PuzzleUnlock',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('unlock_datetime', models.DateTimeField(auto_now_add=True)),
                ('puzzle', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='puzzles.Puzzle')),
                ('team', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='puzzles.Team')),
            ],
            options={
                'unique_together': {('team', 'puzzle')},
            },
        ),
        migrations.CreateModel(
            name='ExtraGuessGrant',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('extra_guesses', models.IntegerField()),
                ('puzzle', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='puzzles.Puzzle')),
                ('team', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='puzzles.Team')),
            ],
            options={
                'unique_together': {('team', 'puzzle')},
            },
        ),
        migrations.CreateModel(
            name='AnswerSubmission',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('submitted_answer', models.CharField(max_length=500)),
                ('is_correct', models.BooleanField()),
                ('submitted_datetime', models.DateTimeField(auto_now_add=True)),
                ('used_free_answer', models.BooleanField()),
                ('puzzle', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='puzzles.Puzzle')),
                ('team', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='puzzles.Team')),
            ],
            options={
                'unique_together': {('team', 'puzzle', 'submitted_answer')},
            },
        ),
    ]
