#!/usr/bin/env python3
"""Opt-in Telegram idle post. SQLite state; no getUpdates consumer or model process."""
import argparse
from contextlib import contextmanager
import datetime as dt
import html
import json
import math
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

from operations import snapshot, timestamp
from storage import Store, dumps, workspace_lock

STATE_KEY = 'telegram_idle_status.v1'
DEFAULTS = {'enabled': False, 'chat_id': '', 'token_env': 'TELEGRAM_BOT_TOKEN',
            'interval_minutes': 30, 'refresh_minutes': 30, 'summary_max_age_minutes': 360,
            'lane_max_age_minutes': 1440, 'timezone': 'UTC'}
REPLACE_SECONDS = 46 * 3600
RETRY_SECONDS = 60


def timezone(name):
    return dt.timezone.utc if name == 'UTC' else ZoneInfo(name)


def settings(st):
    row = st.con.execute("SELECT data FROM records WHERE kind='profile' AND id='workspace'").fetchone()
    profile = json.loads(row[0]) if row else {}
    notification = profile.get('notification', {})
    config = dict(DEFAULTS)
    config.update({key: value for key, value in notification.get('idle_status', {}).items()
                   if key in DEFAULTS and value is not None})
    if type(config['enabled']) is not bool:
        raise ValueError('idle_status.enabled must be a boolean')
    chat_id = config['chat_id']
    if type(chat_id) is int and chat_id > 0:
        chat_id = str(chat_id)
    if not isinstance(chat_id, str) or (chat_id != '' and not re.fullmatch(r'[1-9][0-9]*', chat_id)):
        raise ValueError('Idle status requires a private numeric chat id')
    config['chat_id'] = chat_id
    if not isinstance(config['token_env'], str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', config['token_env']):
        raise ValueError('token_env must name an environment variable, not contain a token')
    for key in ('interval_minutes', 'refresh_minutes', 'summary_max_age_minutes', 'lane_max_age_minutes'):
        value = config[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not 1 <= value <= 10080:
            raise ValueError('Idle status minute settings must be between 1 and 10080')
    try:
        timezone(config['timezone'])
    except (ValueError, KeyError, TypeError):
        raise ValueError('Idle status requires a supported IANA timezone') from None
    return config, profile


def state_read(st):
    row = st.con.execute('SELECT value FROM meta WHERE key=?', (STATE_KEY,)).fetchone()
    state = json.loads(row[0]) if row else {}
    if not isinstance(state, dict):
        raise ValueError('Invalid Telegram status state; inspect before recovery')
    return state


def state_write(st, state):
    with st.transaction():
        st.con.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (STATE_KEY, dumps(state)))


@contextmanager
def locked_store(root):
    # Opening first refuses missing/noncanonical storage rather than initializing it.
    check = Store(root, read_only=True)
    check.close()
    with workspace_lock(root, timeout=35, name='telegram-status.lock'):
        st = Store(root)
        try:
            yield st
        finally:
            st.close()


def render(st, config, current, silence=0):
    st.con.execute('BEGIN')
    try:
        tasks, _, summary = snapshot(st)
    finally:
        st.con.rollback()
    if not summary['ready_for_dispatch']:
        return {'text': '<b>Coordinator status</b>\nState is awaiting migration review.', 'available': False}
    owned, stale = set(), set()
    for lane in summary['active_lanes']:
        key = lane['data'].get('task')
        if key not in tasks or tasks[key]['status'] in ('done', 'dropped'):
            continue
        updated = timestamp(lane['updated_at'])
        if updated is not None and 0 <= current - updated.timestamp() <= config['lane_max_age_minutes'] * 60:
            owned.add(key)
        else:
            stale.add(key)
    stale -= owned
    lines, missing = [], 0
    for key in sorted(owned):
        data = tasks[key]['data']
        sentence, updated = data.get('public_summary'), timestamp(data.get('summary_updated_at'))
        if (not isinstance(sentence, str) or not sentence.strip() or updated is None or
                not 0 <= current - updated.timestamp() < config['summary_max_age_minutes'] * 60):
            missing += 1
            continue
        lines.append('• ' + html.escape(' '.join(sentence.split())[:180], quote=False))
    hidden = max(0, len(lines) - 8)
    lines = lines[:8]
    if hidden:
        lines.append('… and ' + str(hidden) + ' more active tasks.')
    if missing:
        lines.append(str(missing) + ' active task(s) need a current summary.')
    unowned = {key for key, task in tasks.items() if task['status'] in ('in_progress', 'verifying')} - owned
    uncertain = len(stale | unowned)
    if uncertain:
        lines.append(str(uncertain) + ' task(s) need lane/liveness reconciliation.')
    if not lines:
        lines.append('No active work is recorded.')
    updated = dt.datetime.fromtimestamp(current, timezone(config['timezone'])).strftime('%Y-%m-%d %H:%M %Z')
    body = ['<b>Coordinator status</b>', *lines, 'Quiet for ' + str(max(0, int(silence // 60))) + ' min · Updated ' + updated]
    return {'text': '\n'.join(body), 'available': True, 'active_task_count': len(owned),
            'missing_summary_count': missing, 'ownership_review_count': uncertain}


class ApiError(Exception):
    """Safe fixed category only; never retain provider descriptions or token-bearing URLs."""
    def __init__(self, category, retry_after=RETRY_SECONDS):
        super().__init__(category)
        self.category = category
        self.retry_after = retry_after


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class TelegramAPI:
    def __init__(self, config):
        token = os.environ.get(config['token_env'], '')
        if not re.fullmatch(r'[1-9][0-9]*:[A-Za-z0-9_-]+', token):
            raise ValueError('Telegram token environment variable is missing or invalid')
        self.bot_id = token.split(':', 1)[0]  # Public bot identity, not a credential hash.
        self._base = 'https://api.telegram.org/bot' + token + '/'
        self._opener = urllib.request.build_opener(NoRedirect())

    def __call__(self, method, params):
        if method not in ('sendMessage', 'editMessageText', 'deleteMessage'):
            raise ValueError('Unsupported idle status method')
        request = urllib.request.Request(self._base + method, data=json.dumps(params).encode(),
                                         headers={'Content-Type': 'application/json'})
        try:
            try:
                response = self._opener.open(request, timeout=10)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                data = json.loads(response.read(65536))
            if not isinstance(data, dict) or type(data.get('ok')) is not bool:
                raise ValueError('Invalid response')
        except Exception:
            raise ApiError('transport_unknown') from None
        if not data['ok']:
            description = str(data.get('description', '')).lower()
            category = 'api_rejected'
            if 'message is not modified' in description:
                category = 'not_modified'
            elif 'message to delete not found' in description or 'message to edit not found' in description:
                category = 'not_found'
            elif "message can't be deleted" in description or 'message cannot be deleted' in description:
                category = 'cannot_delete'
            retry = data.get('parameters', {}).get('retry_after', RETRY_SECONDS)
            retry = retry if type(retry) is int and 1 <= retry <= 86400 else RETRY_SECONDS
            raise ApiError(category, retry)
        result = data.get('result')
        # This sender edits private-chat posts only, never inline messages (which return True).
        if method in ('sendMessage', 'editMessageText') and (not isinstance(result, dict) or
                type(result.get('message_id')) is not int or result['message_id'] <= 0):
            raise ApiError('transport_unknown')
        if method == 'deleteMessage' and result is not True:
            raise ApiError('transport_unknown')
        return result


class IdleStatus:
    """Inject api_factory and clock for offline tests; production uses only TelegramAPI."""
    def __init__(self, root, api_factory=TelegramAPI, clock=time.time):
        self.root, self.api_factory, self.clock = root, api_factory, clock

    def preview(self):
        st = Store(self.root, read_only=True)
        try:
            config, _ = settings(st)
            state = state_read(st)
            current = self.clock()
            return dict(render(st, config, current, current - state.get('last_exchange_at', current)),
                        enabled=config['enabled'], configured=bool(config['chat_id']), state=state)
        finally:
            st.close()

    def configure(self, values, source):
        if not source.strip():
            raise ValueError('Configuration needs its authorization source')
        if set(values) - set(DEFAULTS):
            raise ValueError('Unknown idle status setting')
        with locked_store(self.root) as st:
            old, profile = settings(st)
            state = state_read(st)
            candidate = dict(old, **values)
            if (state.get('message_id') or state.get('pending')) and any(candidate[k] != old[k] for k in ('chat_id', 'token_env')):
                raise ValueError('Disable and reconcile the previous post before changing its destination')
            notification = dict(profile.get('notification', {}))
            notification['idle_status'] = candidate
            with st.transaction():
                st.put('profile', 'workspace', {'title': profile.get('title', 'Workspace operating profile'),
                       'notification': notification})
                validated, _ = settings(st)
                if validated['enabled'] and not validated['chat_id']:
                    raise ValueError('Enabling Telegram status requires the authorized private chat id')
                st.event('telegram_status_config', 'Idle status configuration updated', source=source)
            # The first enabled interval starts now, never from old installation time.
            if candidate['enabled'] and not old['enabled'] and not state.get('message_id') and not state.get('pending'):
                state.update(last_exchange_at=self.clock(), exchange_seq=state.get('exchange_seq', 0) + 1)
                state.pop('next_attempt_at', None)
                state_write(st, state)
            return validated

    def exchange(self, direction, event_id, at=None):
        if direction not in ('inbound', 'outbound') or not isinstance(event_id, str) or not event_id.strip() or len(event_id) > 200:
            raise ValueError('Exchange needs inbound/outbound and a stable event id')
        current = self.clock()
        occurred = timestamp(at).timestamp() if at and timestamp(at) else current if at is None else None
        if occurred is None or occurred > current + 5:
            raise ValueError('Exchange timestamp must be timezone-aware and not in the future')
        with locked_store(self.root) as st:
            config, _ = settings(st)
            if not config['chat_id']:
                raise ValueError('Configure the authorized chat before recording exchanges')
            state = state_read(st)
            key = dumps(['telegram_exchange', config['chat_id'], direction, event_id])
            if st.con.execute('SELECT 1 FROM events WHERE dedupe_key=?', (key,)).fetchone():
                return {'duplicate': True}
            baseline = state.get('last_exchange_at', current)
            if occurred >= baseline:
                state.update(last_exchange_at=max(occurred, baseline), exchange_seq=state.get('exchange_seq', 0) + 1)
                # A real exchange should not wait on an earlier post/edit backoff.
                state.pop('next_attempt_at', None)
            else:
                state.setdefault('last_exchange_at', baseline)
            with st.transaction():
                st.event('telegram_exchange', direction + ' exchange accepted', ref=event_id, key=key)
                st.con.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (STATE_KEY, dumps(state)))
            return {'duplicate': False, 'historical': occurred < baseline}

    def reconcile(self, message_id=None, absent=False, source=''):
        if not source.strip() or (type(message_id) is not int or message_id <= 0) and not absent:
            raise ValueError('Reconciliation needs observed message id or absence and evidence source')
        with locked_store(self.root) as st:
            state = state_read(st)
            if not state.get('pending') and not state.get('message_id'):
                raise ValueError('No outstanding post to reconcile')
            pending = state.get('pending', {})
            if absent:
                self._clear(state)
            else:
                state.update(message_id=message_id, posted_at=pending.get('at', state.get('posted_at', self.clock())),
                             updated_at=self.clock(), post_exchange_seq=pending.get('exchange_seq', state.get('post_exchange_seq', 0)))
                state.pop('pending', None)
                state.pop('error', None)
                state.pop('next_attempt_at', None)
            state_write(st, state)
            with st.transaction():
                st.event('telegram_status_reconciled', 'Observed absent post' if absent else 'Observed post adopted', source=source)
            return {'reconciled': True}

    @staticmethod
    def _clear(state):
        for key in ('message_id', 'posted_at', 'updated_at', 'post_exchange_seq', 'pending', 'error', 'next_attempt_at'):
            state.pop(key, None)

    def _call(self, st, state, api, config, method, current, text=None):
        params = {'chat_id': config['chat_id']}
        if method != 'sendMessage':
            params['message_id'] = state['message_id']
        if text is not None:
            params.update(text=text, parse_mode='HTML', link_preview_options={'is_disabled': True})
        if method == 'sendMessage':
            params['disable_notification'] = True
        state['pending'] = {'method': method, 'at': current, 'exchange_seq': state.get('exchange_seq', 0)}
        state_write(st, state)  # Journal before the external action, including before a crash.
        try:
            result = api(method, params)
            if method == 'sendMessage' and (not isinstance(result, dict) or type(result.get('message_id')) is not int or result['message_id'] <= 0):
                raise ApiError('transport_unknown')
        except Exception as error:
            category = error.category if isinstance(error, ApiError) else 'transport_unknown'
            if method == 'editMessageText' and category == 'not_modified':
                result = None
            elif category == 'not_found' and method in ('editMessageText', 'deleteMessage'):
                self._clear(state)
                state_write(st, state)
                return True
            else:
                state['error'] = category
                if method != 'sendMessage' or category != 'transport_unknown':
                    state.pop('pending', None)
                state['next_attempt_at'] = current + (error.retry_after if isinstance(error, ApiError) else RETRY_SECONDS)
                state_write(st, state)
                return False
        if method == 'deleteMessage':
            self._clear(state)
        else:
            if method == 'sendMessage':
                state.update(message_id=result['message_id'], posted_at=current,
                             post_exchange_seq=state.get('exchange_seq', 0))
            state['updated_at'] = current
            for key in ('pending', 'error', 'next_attempt_at'):
                state.pop(key, None)
        state_write(st, state)
        return True

    def tick(self):
        with locked_store(self.root) as st:
            config, _ = settings(st)
            state = state_read(st)
            current = self.clock()
            if state.get('pending', {}).get('method') == 'sendMessage':
                return {'action': 'reconcile_send', 'error': 'delivery_unknown'}
            if state.get('error') == 'cannot_delete':
                return {'action': 'reconcile_cleanup', 'error': 'cannot_delete'}
            if not config['enabled'] and not state.get('message_id'):
                return {'action': 'disabled'}
            if not config['chat_id']:
                raise ValueError('Telegram status has no configured recipient')
            state.setdefault('last_exchange_at', current)
            state.setdefault('exchange_seq', 0)
            # Credentials are loaded only for an enabled feed or cleanup of its own post.
            api = self.api_factory(config)
            identity = [str(api.bot_id), config['chat_id']]
            if state.get('identity') not in (None, identity) and (state.get('message_id') or state.get('pending')):
                raise ValueError('Bot/chat identity changed; reconcile the original post with its original configuration')
            state['identity'] = identity
            state_write(st, state)
            if state.get('next_attempt_at', 0) > current:
                return {'action': 'backoff'}
            pending = state.get('pending', {}).get('method')
            mid = state.get('message_id')
            if mid and (not config['enabled'] or state.get('post_exchange_seq') != state['exchange_seq'] or
                        current - state.get('posted_at', current) >= REPLACE_SECONDS or pending == 'deleteMessage'):
                if not self._call(st, state, api, config, 'deleteMessage', current):
                    return {'action': 'retry_delete', 'error': state.get('error')}
                if not config['enabled'] or current - state['last_exchange_at'] < config['interval_minutes'] * 60:
                    return {'action': 'deleted'}
            if current - state['last_exchange_at'] < config['interval_minutes'] * 60:
                return {'action': 'waiting'}
            if state.get('message_id') and current - state.get('updated_at', 0) < config['refresh_minutes'] * 60 and pending != 'editMessageText':
                return {'action': 'waiting'}
            content = render(st, config, current, current - state['last_exchange_at'])
            if not content['available']:
                return {'action': 'state_unavailable'}
            method = 'editMessageText' if state.get('message_id') else 'sendMessage'
            success = self._call(st, state, api, config, method, current, content['text'])
            if success and method == 'editMessageText' and not state.get('message_id'):
                return {'action': 'missing'}
            return {'action': ('edited' if method == 'editMessageText' else 'posted') if success else
                    ('reconcile_send' if state.get('pending') else 'retry'), 'error': state.get('error')}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('preview'); commands.add_parser('tick')
    runner = commands.add_parser('run'); runner.add_argument('--poll-seconds', type=int, default=15)
    configure = commands.add_parser('configure')
    configure.add_argument('--chat-id', required=True)
    configure.add_argument('--token-env', default='TELEGRAM_BOT_TOKEN')
    configure.add_argument('--timezone', default='UTC')
    configure.add_argument('--interval-minutes', type=int, default=30)
    configure.add_argument('--refresh-minutes', type=int, default=30)
    configure.add_argument('--summary-max-age-minutes', type=int, default=360)
    configure.add_argument('--lane-max-age-minutes', type=int, default=1440)
    configure.add_argument('--source', required=True)
    disable = commands.add_parser('disable'); disable.add_argument('--source', required=True)
    exchange = commands.add_parser('exchange')
    exchange.add_argument('--direction', choices=('inbound', 'outbound'), required=True)
    exchange.add_argument('--event-id', required=True); exchange.add_argument('--at')
    reconcile = commands.add_parser('reconcile')
    observed = reconcile.add_mutually_exclusive_group(required=True)
    observed.add_argument('--message-id', type=int); observed.add_argument('--absent', action='store_true')
    reconcile.add_argument('--source', required=True)
    args = parser.parse_args(argv)
    engine = IdleStatus(args.root)
    try:
        if args.command == 'configure':
            result = engine.configure({'enabled': True, 'chat_id': args.chat_id, 'token_env': args.token_env,
                                       'timezone': args.timezone, 'interval_minutes': args.interval_minutes,
                                       'refresh_minutes': args.refresh_minutes,
                                       'summary_max_age_minutes': args.summary_max_age_minutes,
                                       'lane_max_age_minutes': args.lane_max_age_minutes}, args.source)
        elif args.command == 'disable':
            result = engine.configure({'enabled': False}, args.source)
        elif args.command == 'exchange':
            result = engine.exchange(args.direction, args.event_id, args.at)
        elif args.command == 'reconcile':
            result = engine.reconcile(args.message_id, args.absent, args.source)
        elif args.command == 'run':
            if not 1 <= args.poll_seconds <= 60:
                raise ValueError('poll-seconds must be between 1 and 60')
            previous = None
            while True:
                result = engine.tick()
                if result != previous:
                    print(dumps(result), flush=True)
                    previous = result
                time.sleep(args.poll_seconds)
        else:
            result = getattr(engine, args.command)()
        print(dumps(result))
        return 2 if result.get('action') in ('reconcile_send', 'reconcile_cleanup', 'retry', 'retry_delete', 'state_unavailable') else 0
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        # Never echo arbitrary exception text: urllib and unexpected libraries can include tokens.
        print('telegram-status: operation failed (' + type(error).__name__ + '); check configuration and preview', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
