#!/usr/bin/env python
# -*- encoding: utf-8 -*-
# vim: set et sw=4 ts=4 sts=4 ff=unix fenc=utf8:
# Author: Binux<i@binux.me>
#         http://binux.me
# Created on 2014-02-16 22:24:20

import os
import six
import sys
import imp
import time
import weakref
import logging
import inspect
import traceback
import linecache

import sys,os
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from sspider.libs import utils
from sspider.libs.log import SaveLogHandler, LogFormatter
logger = logging.getLogger("processor")


class ProjectManager(object):
    """
    load projects from projectdb, update project
    """

    CHECK_PROJECTS_INTERVAL = 5 * 60
    RELOAD_PROJECT_INTERVAL = 60 * 60



    def __init__(self, projectdb, env):
        self.projectdb = projectdb
        self.env = env

        self.projects = {}
        self.last_check_projects = time.time()

    def _need_update(self, project_name, updatetime=None, md5sum=None):
        '''Check if project_name need update'''
        if project_name not in self.projects:
            return True
        elif md5sum and md5sum != self.projects[project_name]['info'].get('md5sum'):
            return True
        elif updatetime and updatetime > self.projects[project_name]['info'].get('updatetime', 0):
            return True
        elif time.time() - self.projects[project_name]['load_time'] > self.RELOAD_PROJECT_INTERVAL:
            return True
        return False

    def _check_projects(self):
        '''Check projects by last update time'''
        for project in self.projectdb.check_update(self.last_check_projects,
                                                   ['name', 'updatetime']):
            if project['name'] not in self.projects:
                continue
            if project['updatetime'] > self.projects[project['name']]['info'].get('updatetime', 0):
                self._update_project(project['name'])
        self.last_check_projects = time.time()

    def _update_project(self, project_name):
        '''Update one project from database'''
        project = self.projectdb.get(project_name)
        if not project:
            return None
        return self._load_project(project)

    def _load_project(self, project):
        '''Load project into self.projects from project info dict'''
        try:
            project['md5sum'] = utils.md5string(project['script'])
            ret = {
                'loader': None,
                'module': None,
                'class': None,
                'instance': None,
                'exception': None,
                'exception_log': traceback.format_exc(),
                'info': project,
                'load_time': time.time(),
            }
            self.projects[project['name']] = ret
        except Exception as e:
            logger.exception("load project %s error", project.get('name', None))
            ret = {
                'loader': None,
                'module': None,
                'class': None,
                'instance': None,
                'exception': e,
                'exception_log': traceback.format_exc(),
                'info': project,
                'load_time': time.time(),
            }
            self.projects[project['name']] = ret
            return False
        logger.debug('project: %s updated.', project.get('name', None))
        return True

    def get(self, project_name, updatetime=None, md5sum=None):
        '''get project data object, return None if not exists'''
        if time.time() - self.last_check_projects > self.CHECK_PROJECTS_INTERVAL:
            self._check_projects()
        if self._need_update(project_name, updatetime, md5sum):
            self._update_project(project_name)
        return self.projects.get(project_name, None)


class ProjectFinder(object):
    '''ProjectFinder class for sys.meta_path'''

    def __init__(self, projectdb):
        self.get_projectdb = weakref.ref(projectdb)

    @property
    def projectdb(self):
        return self.get_projectdb()

    def find_module(self, fullname, path=None):
        if fullname == 'projects':
            return self
        parts = fullname.split('.')
        if len(parts) == 2 and parts[0] == 'projects':
            name = parts[1]
            if not self.projectdb:
                return
            info = self.projectdb.get(name)
            if info:
                return ProjectLoader(info)

    def load_module(self, fullname):
        mod = imp.new_module(fullname)
        mod.__file__ = '<projects>'
        mod.__loader__ = self
        mod.__path__ = ['<projects>']
        mod.__package__ = 'projects'
        return mod

    def is_package(self, fullname):
        return True


class ProjectLoader(object):
    '''ProjectLoader class for sys.meta_path'''

    def __init__(self, project, mod=None):
        self.project = project
        self.name = project['name']
        self.mod = mod

    def load_module(self, fullname):
        if self.mod is None:
            self.mod = mod = imp.new_module(fullname)
        else:
            mod = self.mod
        mod.__file__ = '<%s>' % self.name
        mod.__loader__ = self
        mod.__project__ = self.project
        mod.__package__ = ''
        code = self.get_code(fullname)
        six.exec_(code, mod.__dict__)
        linecache.clearcache()
        return mod

    def is_package(self, fullname):
        return False

    def get_code(self, fullname):
        return compile(self.get_source(fullname), '<%s>' % self.name, 'exec')

    def get_source(self, fullname):
        script = self.project['script']
        if isinstance(script, six.text_type):
            return script.encode('utf8')
        return script
