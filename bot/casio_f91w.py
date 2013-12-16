#!/usr/bin/env python

__version__ = '0.2'
__author__ = 'Joost Molenaar <j.j.molenaar@gmail.com>'

# Version history:
# 0.1    initial version with hourly beep and alarm
# 0.2    moved twitter code to module twitter.py

import time
import re
import datetime

import pytz

import twitter

CET = pytz.timezone('Europe/Amsterdam')
UTC = pytz.utc

class CasioF91W(object):
    DAYS = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU']
    MSG = u'BEEP BEEP! {0} {1} {2:02}:{3:02}:00'

    R1 = re.compile(r'alarm ([01]?[0-9]|2[0-3]):([0-5][0-9]) ([+-])([01][0-9]|2[0-3])([0-5][0-9])')
    R2 = re.compile(r'alarm (0?[1-9]|1[0-2]):([0-5][0-9]) (AM|PM) ([+-])([01][0-9]|2[0-3])([0-5][0-9])')
    R3 = re.compile(r'alarm (0?[1-9]|1[0-2]):([0-5][0-9]) (AM|PM)')
    R4 = re.compile(r'alarm ([01]?[0-9]|2[0-3]):([0-5][0-9])')

    def __init__(self, name, api=None):
        self.name = name
        self.api = api if api else twitter.TwitterAPI(name)

    def send_beep(self, date):
        try:
            status = self.MSG.format(self.DAYS[date.tm_wday], date.tm_mday, date.tm_hour, date.tm_min)
            self.api.log('Posting status: {0} ({1})', repr(status), len(status))
            self.api.post_statuses_update(status=status)
            return True
        except twitter.FailWhale as fail:
            fail.log_error(self.api)
            return False

    def save_alarm(self, alarm, mention):
        key = '{0:02}:{1:02}'.format(*alarm)
        m_id, m_sn = mention['id'], mention['user']['screen_name']
        if key not in self.api.config['alarms']:
            self.api.config['alarms'][key] = {}
        self.api.config['alarms'][key][m_id] = m_sn

    def parse_tweet_for_alarm(self, tweet):
        id, screen_name, text = tweet['id'], tweet['user']['screen_name'], tweet['text']

        match = self.R1.search(text) # hh:mm <+|->hhmm
        if match:
            self.api.log('Alarm: #{0} from @{1}: {2} --> {3}', id, screen_name, repr(text), match.groups())
            th, tm, sign, zh, zm = match.groups()
            th, tm = int(th), int(tm)
            zh, zm = int(zh), int(zm)
            sign = +1 if sign == '+' else -1
            base = datetime.datetime.combine(datetime.date.today(), datetime.time(hour=th, minute=tm)).replace(tzinfo=UTC)
            offset = sign * datetime.timedelta(hours=zh, minutes=zm)
            d = (base - offset).astimezone(CET)
            return ((d.hour, d.minute), tweet)
        
        match = self.R2.search(text) # hh:mm <AM|PM> <+|->hhmm
        if match:
            th, tm, am_pm, sign, zh, zm = match.groups()
            th, tm = int(th), int(tm)
            zh, zm = int(zh), int(zm)
            sign = +1 if sign == '+' else -1
            if am_pm == 'AM' and th == 12: th -= 12
            if am_pm == 'PM' and th  < 12: th += 12
            base = datetime.datetime.combine(datetime.date.today(), datetime.time(hour=th, minute=tm)).replace(tzinfo=UTC)
            offset = sign * datetime.timedelta(hours=zh, minutes=zm)
            d = (base - offset).astimezone(CET)
            return ((d.hour, d.minute), tweet)

        match = self.R3.search(text) # hh:mm <AM|PM>
        if match:
            th, tm, am_pm = match.groups()
            th, tm = int(th), int(tm)
            if am_pm == 'AM' and th == 12: th -= 12
            if am_pm == 'PM' and th  < 12: th += 12
            return ((th, tm), tweet)

        match = self.R4.search(text) # hh:mm
        if match:
            self.api.log('Alarm: #{0} from @{1}: {2} --> {3}', id, screen_name, repr(text), match.groups())
            th, tm = match.groups()
            th, tm = int(th), int(tm)
            return ((th, tm), tweet)

        return (None, tweet)
            
    def get_mentions(self):
        last_mention = self.api.config['last_mention']
        if last_mention:
            mentions = self.api.get_statuses_mentions_timeline(count=200, since_id=last_mention)
        else:
            mentions = self.api.get_statuses_mentions_timeline(count=200)
        if mentions:
            self.api.config['last_mention'] = str(max(int(m['id']) for m in mentions))
        return mentions

    def handle_mentions(self, t):
        try:
            dirty = False
            for m in self.get_mentions():
                alarm, mention = self.parse_tweet_for_alarm(m)
                if alarm:
                    self.save_alarm(alarm, mention)
                    dirty = True
            if dirty:
                self.api.save()
            return True
        except twitter.FailWhale as fail:
            fail.log_error(self.api)
            return False

    def send_alarms(self, t):
        key = '{0:02}:{1:02}'.format(t.tm_hour, t.tm_min)
        if key in self.api.config['alarms']:
            for (tid, screen_name) in self.api.config['alarms'][key].items():
                status = u'@{0}'.format(screen_name)
                while len(status) < 130:
                    status += u' BEEP BEEP!'
                try:
                    self.api.log('Posting status: {0} ({1})', repr(status), len(status))
                    self.api.post_statuses_update(status=status, in_reply_to_status_id=tid)
                    del self.api.config['alarms'][key][tid]
                except twitter.FailWhale as fail:
                    fail.log_error(self.api)
                if not self.api.config['alarms'][key]:
                    del self.api.config['alarms'][key]
            self.api.save()
        return True