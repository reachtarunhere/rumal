#!/usr/bin/env python
#
# fdaemon.py
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston,
# MA  02111-1307  USA
#
# Author:   Tarun Kumar <reach.tarun.here@gmail.com>
# NOTE: THIS IS AN INITIAL RELEASE AND IS LIKELY TO BE UNSTABLE

import logging
import os
import time
import requests

from datetime import datetime
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from interface.models import *
from interface.api import TaskResource

import pymongo
from bson import ObjectId
from bson.json_util import loads,dumps

# import json
#Connection settings to be done manually
BACKEND_HOST = ""
API_KEY = ""
API_USER = ""

TASK_POST_URL = BACKEND_HOST + "/api/v1/task/"


client = pymongo.MongoClient()
db = client.thug

logger = logging.getLogger(__name__)

class InvalidMongoIdException(Exception):
    pass

class Command(BaseCommand):

    def fetch_new_tasks(self):
        return Task.objects.filter(status__exact=STATUS_NEW).order_by('submitted_on')

    def fetch_pending_tasks(self):
        Task.objects.filter(status__exact=STATUS_PROCESSING)
        # Task.objects.filter(status__exact=STATUS_PROCESSING).update(status=STATUS_NEW)

    def mark_as_running(self, task):
        logger.debug("[{}] Marking task as running".format(task.id))
        task.started_on = datetime.now(pytz.timezone(settings.TIME_ZONE))
        task.status = STATUS_PROCESSING
        task.save()

    def mark_as_failed(self, task):
        logger.debug("[{}] Marking task as failed".format(task.id))
        task.completed_on = datetime.now(pytz.timezone(settings.TIME_ZONE))
        task.status = STATUS_FAILED
        task.save()

    def mark_as_completed(self, task):
        logger.debug("[{}] Marking task as completed".format(task.id))
        task.completed_on = datetime.now(pytz.timezone(settings.TIME_ZONE))
        task.status = STATUS_COMPLETED
        task.save()

    def post_new_task(self,task):
        t = TaskResource()
        temp = loads(t.renderDetail(task.id))
        temp.pop("user")
        temp.pop("sharing_model")
        temp["frontend_id"] = temp.pop("id")
        post_data = dumps(temp)
        headers = {'Content-type': 'application/json', 'Authorization': 'ApiKey {}:{}'.format(API_USER,API_KEY)}
        r = requests.post(TASK_POST_URL, json.dumps(post_data), headers=headers)
        if r.status_code == 201:
            self.mark_as_running(task)

    def retrive_save_document(self,analysis_id):
        combo_resource_url = BACKEND_HOST + "/api/v1/analysiscombo/{}/?format=json".format(analysis_id)
        retrive_headers = {'Authorization': 'ApiKey {}:{}'.format(API_USER,API_KEY)}
        r = requests.get(combo_resource_url, headers = retrive_headers)
        response = loads(r.json())
        frontend_analysis_id = db.analysiscombo.insert(response)
        return frontend_analysis_id

    def get_backend_status(self,pending_id_list):
        semicolon_seperated = ";".join(pending_id_list) + ";"
        status_headers = {'Authorization': 'ApiKey {}:{}'.format(API_USER,API_KEY)}
        status_url = BACKEND_HOST + "/api/v1/status/set/{}/?format=json".format(semicolon_sepearated)
        r = requests.get(status_url, headers=status_headers)
        response = loads(r.json())
        finished_on_backend = [x for x in response["objects"] if x["status"] == 1]
        return finished_on_backend

    def handle(self, *args, **options):
        logger.info("Starting up frontend daemon")
        while True:
            logger.debug("Fetching new tasks to post to backend.")
            tasks = self.fetch_new_tasks()
            logger.debug("Got {} new tasks".format(len(tasks)))
            for task in tasks:
                # self._mark_as_running(task)
                self.post_new_task(task)
            logger.debug("Fetching pending tasks posted to backend.")
            tasks = self.fetch_pending_tasks()
            pending_id_list = [str(x.id) for x in tasks]
            finished_on_backend = self.get_backend_status(pending_id_list)
            for x in finished_on_backend:
                frontend_analysis_id = retrive_save_document(x["object_id"])
                task = Task.objects.get(id=x["frontend_id"])
                task.analysis_id = frontend_analysis_id
                task.save()
                self.mark_as_completed(task)
            logger.info("Sleeping for {} seconds".format(60))
            time.sleep(60)