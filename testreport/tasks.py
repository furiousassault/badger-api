from __future__ import absolute_import

from testreport.models import Launch, FINISHED, STOPPED, CELERY_FINISHED_STATES
from testreport.models import Bug

from rest_framework.exceptions import APIException
import requests

import celery

import os
import stat
import json
from django.utils import timezone
from django.conf import settings
from datetime import timedelta, datetime
from time import sleep


import logging
log = logging.getLogger(__name__)


@celery.task()
def finalize_launch(launch_id, state=FINISHED, timeout=30, tries=5):
    log.info("Finalize launch {}".format(launch_id))
    launch = Launch.objects.get(pk=launch_id)
    log.info("Current launch: {}".format(launch.__dict__))
    launch.finished = datetime.now()
    launch.calculate_counts()
    launch.state = state
    log.info("Launch for update: {}".format(launch.__dict__))
    launch.save(force_update=True)
    if state != STOPPED:
        for i in range(0, tries):
            log.info("Waiting for {} seconds, before next try".format(timeout))
            sleep(timeout)
            launch = Launch.objects.get(pk=launch_id)
            if launch.state == state:
                break
            log.info("Launch state not finished, try to save again.")
            launch.finished = datetime.now()
            launch.state = state
            launch.save()
    log.info(
        "Updated launch: {}".format(Launch.objects.get(pk=launch_id).__dict__))


@celery.task()
def create_environment(environment_vars, json_file):
    workspace_path = environment_vars['WORKSPACE']
    # Create workspace directory
    if not os.path.exists(workspace_path):
        os.makedirs(workspace_path)
    os.chmod(workspace_path,
             stat.S_IRWXU | stat.S_IRWXG | stat.S_IROTH | stat.S_IXOTH)

    # Write json file
    json_file_path = os.path.join(workspace_path, 'file.json')
    with open(json_file_path, 'w+') as f:
        f.write(json.dumps(json_file))

    # Write environment file
    env_file_path = os.path.join(workspace_path, 'environments.sh')
    output = ''
    for key, value in iter(environment_vars.items()):
        output += 'export {key}="{value}"\n'.format(key=key, value=value)
    with open(env_file_path, 'w+') as f:
        f.write(output)


@celery.task()
def finalize_broken_launches():
    log.debug("Finalize broke launches...")

    def is_finished(launch):
        log.debug("Check {} is finished".format(launch))
        for k, v in iter(launch.get_tasks().items()):
            res = celery.result.AsyncResult(k)
            if res.state not in CELERY_FINISHED_STATES:
                return False
        return True

    def process(launch):
        if is_finished(launch):
            finalize_launch(launch.id)
        return launch

    return list(map(process, Launch.objects.filter(state__exact=0)))


@celery.task()
def cleanup_database():
    days = timezone.now().date() - timedelta(
        days=settings.STORE_TESTRESULTS_IN_DAYS)

    map(lambda launch: launch.testresult_set.all().delete(),
        Launch.objects.filter(finished__lte=days))


@celery.task()
def update_bugs():
    if settings.JIRA_INTEGRATION:
        for bug in Bug.objects.all():
            update_state(bug)
    else:
        log.info('Jira integration is off. '
                 'If you want to use this feature, turn it on.')


def update_state(bug):
    log.debug('Starting bug "{}" update'.format(bug.externalId))
    now = datetime.utcnow()
    td = now - datetime.replace(bug.updated, tzinfo=None)
    diff = (td.microseconds +
            (td.seconds + td.days * 24 * 3600) * 10**6) / 10**6

    if bug.state in settings.BUG_STATE_EXPIRED:
        old_state = bug.state
        new_state = _get_state_from_bts(bug)
        log.debug('Comparing bug state,'
                  '"{0}" and "{1}"'.format(old_state, new_state))
        if old_state == new_state and diff > settings.BUG_TIME_EXPIRED:
            log.debug(
                'Bug "{}" expired, deleting it from DB'.format(bug.externalId))
            bug.delete()
        elif old_state == new_state and diff < settings.BUG_TIME_EXPIRED:
            log.debug(
                'Bug "{}" not updated, '
                'because {} seconds not expired'.format(
                    bug.externalId, settings.BUG_TIME_EXPIRED))
        else:
            bug.state = new_state
            bug.updated = now
            log.debug('Saving bug "{}"'.format(bug.externalId))
            bug.save()
    if bug.state not in settings.BUG_STATE_EXPIRED \
            and diff > settings.TIME_BEFORE_UPDATE_BUG_INFO:
        log.debug("%s > %s time to update bug state.", diff,
                  settings.TIME_BEFORE_UPDATE_BUG_INFO)
        bug.updated = now
        bug.state = _get_state_from_bts(bug)
        log.debug('Saving bug "{}"'.format(bug.externalId))
        bug.save()


def get_name_from_bts(bug):
    log.debug('Get name for bug "{}"'.format(bug.externalId))
    return _get_bug(bug.externalId)['fields']['summary']


def _get_state_from_bts(bug):
    log.debug('Get state for bug {}'.format(bug.externalId))
    return _get_bug(bug.externalId)['fields']['status']['name']


def _get_bug(bug_id):
    response = requests.get(
        'https://{}{}'.format(
            settings.BUG_TRACKING_SYSTEM_HOST,
            settings.BUG_TRACKING_SYSTEM_BUG_PATH.format(issue_id=bug_id)),
        auth=(settings.BUG_TRACKING_SYSTEM_LOGIN,
              settings.BUG_TRACKING_SYSTEM_PASSWORD),
        headers={'Content-Type': 'application/json'})
    data = response.json()
    log.debug(data)
    errors = []
    if 'errors' in data:
        errors += data['errors']
    if 'errorMessages' in data:
        errors += data['errorMessages']
    if len(errors) != 0:
        errors = map(lambda x: x.encode('utf-8', errors='replace'), errors)
        raise APIException(
            "Bug tracking system: '{}'".format('\n'.join(errors)))
    return data
