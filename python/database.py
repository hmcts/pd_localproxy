# -*- coding: utf-8 -*-
"""MySQL/MariaDB access using the PyMySQL already deployed with XHIBIT."""
def unquote(value):
    # Strip one matching pair of surrounding quotes, as http_support.read_ini does.
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


class Database(object):
    def __init__(self, connection, name, profile=None):
        self.connection = connection
        self.name = name
        self.profile = profile
        self.progress = []
        self._progress_connected = False

    def progress_open(self):
        if not self._progress_connected:
            self.progress.append('DB Connected.')
            self._progress_connected = True

    @classmethod
    def from_values(cls, values):
        import pymysql
        if values.get('DBType', 'mysql').lower() != 'mysql':
            raise ValueError('Only the deployed MySQL/MariaDB contract is supported')
        dsn = unquote(values['DBConn'])
        if not dsn.startswith('mysql:'):
            raise ValueError('DBConn must be a mysql DSN')
        fields = dict(part.split('=', 1) for part in dsn[6:].split(';') if '=' in part)
        options = dict(host=fields.get('host', 'localhost'),
                       port=int(fields.get('port', 3306)), user=values['DBusername'],
                       password=values['DBpasswd'], db=values['DBName'],
                       charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor,
                       connect_timeout=10)
        if fields.get('unix_socket'):
            options['unix_socket'] = fields['unix_socket']
        return cls(pymysql.connect(**options), values['DBName'])

    @classmethod
    def from_parser_config(cls, config):
        values = dict((key, unquote(config['DATABASE'].get(key, '')))
                      for key in ('DBConn', 'DBName', 'DBusername', 'DBpasswd', 'DBType'))
        values['DBType'] = values['DBType'] or 'mysql'
        return cls.from_values(values)

    def query(self, sql, args=()):
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, args)
            return cursor.fetchall()
        finally:
            cursor.close()

    def execute(self, sql, args=()):
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, args)
            return cursor.rowcount
        finally:
            cursor.close()

    def columns(self):
        if self.profile is None:
            rows = self.query('SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS '
                              'WHERE TABLE_SCHEMA=%s', (self.name,))
            self.profile = {}
            for row in rows:
                self.profile.setdefault(row['TABLE_NAME'].lower(), set()).add(row['COLUMN_NAME'].lower())
        return self.profile

    def has(self, table, column):
        return column.lower() in self.columns().get(table.lower(), set())

    def parser_row(self, mac):
        missing = self.validate_schema()
        if missing:
            raise ValueError('Required Model Court database structure missing')
        sql = ('SELECT CDU.cduNumber AS title, CDU.location, CDU.notification, CDU.macAddress, '
               'urlMappings.url AS url, CDU.refresh, SITE.title AS site, SITE.pageUrl, '
               'SITE.powersaveSchedule, SITE.welshTitle AS welshTitle FROM CDU '
               'JOIN SITE ON CDU.fkSITE=SITE.id '
               'JOIN urlMappings ON urlMappings.cduID=CDU.id ')
        rows = self.query(sql + 'WHERE UPPER(CDU.macAddress)=%s', (mac.upper(),))
        return rows[0] if len(rows) == 1 else None

    def index(self):
        self.progress_open()
        self.progress.append('Opened DB.')
        rows = self.query('SELECT CDU.id AS CDUid, SITE.id AS SITEid, SITE.title AS site, '
                          'CDU.title FROM CDU JOIN SITE ON SITE.id=CDU.fkSITE '
                          'ORDER BY SITEid, CDUid ASC')
        self.progress.extend(['Executed DB.', 'Fetched {0} records.'.format(len(rows))])
        return rows

    def site(self, identifier):
        self.progress_open()
        rows = self.query('SELECT id,title,xsl,selectorUrl,pageUrl,alert,powersaveSchedule '
                          'FROM SITE WHERE id=%s', (identifier,))
        if rows:
            self.progress.append('Fetched SITE detail having index [{0}].'.format(identifier))
        return rows[0] if rows else None

    def cdu(self, identifier):
        self.progress_open()
        rows = self.query('SELECT CDU.*, SITE.title AS site, SITE.selectorUrl FROM CDU '
                          'JOIN SITE ON SITE.id=CDU.fkSITE WHERE CDU.id=%s', (identifier,))
        if not rows:
            return None
        row = rows[0]
        self.progress.append('Fetched CDU detail having index [{0}].'.format(identifier))
        # The supplied manager reads CDU.url even when the parser reads urlMappings.
        # Preserve that distinction; synchronizing the two is a separate behavioural fix.
        return row

    def history(self, identifier, maximum):
        self.progress.append('Opened DB for fetchIpHistory.')
        rows = self.query('SELECT ipAddress, ts FROM MAC_TO_IP WHERE fkCDU=%s '
                          'ORDER BY ts DESC LIMIT %s', (identifier, int(maximum)))
        self.progress.extend(['Executed DB.', 'Fetched {0} records.'.format(len(rows))])
        return rows

    def selector(self, identifier):
        self.progress.append('Opened DB for fetchIpHistory.')
        rows = self.query('SELECT SITE.selectorUrl FROM SITE JOIN CDU ON CDU.fkSITE=SITE.id '
                          'WHERE CDU.id=%s', (identifier,))
        self.progress.append('Executed DB.')
        value = rows[0]['selectorUrl'] if rows else ''
        self.progress.append('Fetched Selector URL ({0}) for CDU having index [{1}].'.format(value, identifier))
        return value

    def audit(self, user, event, data=''):
        self.execute('INSERT INTO AUDIT (username,eventType,eventData) VALUES (%s,%s,%s)',
                     (user, event, data))
        self.connection.commit()

    def update_site(self, identifier, values):
        self.progress_open()
        args = [values.get(key, '') for key in ('title', 'xsl', 'alert', 'selectorURL',
                                                'pageURL', 'powersaveSchedule')]
        args[1] = args[1] or None
        args[2] = None if args[2] in ('', 'undefined') else args[2]
        self.progress.append('Updating SITE with index [{0}] with title({1}), xsl({2}) and alert ({3}).'.format(
            identifier, args[0], args[1] or '', args[2] or ''))
        try:
            self.execute('UPDATE SITE SET title=%s,xsl=%s,alert=%s,selectorUrl=%s,'
                         'pageUrl=%s,powersaveSchedule=%s WHERE id=%s', tuple(args + [identifier]))
            self.connection.commit()
            self.progress.append('Full update to SITE with index [{0}].'.format(identifier))
        except Exception:
            self.connection.rollback()
            raise

    def update_cdu(self, identifier, values):
        self.progress_open()
        args = [values.get(key, '') for key in ('macAddress', 'title', 'description',
                                                'location', 'url', 'xsl', 'refresh')]
        args[5] = args[5] or None
        try:
            self.execute('UPDATE CDU SET macAddress=%s,title=%s,description=%s,location=%s,'
                         'url=%s,xsl=%s,refresh=%s WHERE id=%s', tuple(args + [identifier]))
            self.connection.commit()
            self.progress.append('Full update to CDU with index [{0}].'.format(identifier))
        except Exception:
            self.connection.rollback()
            raise

    def notice(self, identifier, value):
        self.progress_open()
        try:
            self.execute('UPDATE CDU SET notification=%s WHERE id=%s', (value, identifier))
            self.connection.commit()
            self.progress.append('Notification updated to CDU with index [{0}].'.format(identifier))
        except Exception:
            self.connection.rollback()
            raise

    def validate_schema(self, with_manager=False):
        required = {
            'site': 'id title welshTitle pageUrl powersaveSchedule',
            'cdu': 'id macAddress cduNumber location refresh notification fkSITE',
            'urlmappings': 'cduID url'}
        if with_manager:
            required['site'] += ' xsl alert selectorUrl'
            required['cdu'] += ' title description url ipAddr xsl'
            required['mac_to_ip'] = 'ipAddress fkCDU ts'
            required['audit'] = 'username eventType eventData'
        missing = []
        for table, names in required.items():
            missing.extend(table + '.' + name for name in names.split() if not self.has(table, name))
        return missing

    def close(self):
        self.connection.close()
