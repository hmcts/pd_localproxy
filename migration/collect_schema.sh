#!/bin/bash
# Metadata queries only: no case rows, DDL changes, table locks or password files.
set -eu
umask 077
if [ "$#" -ne 2 ]; then
    echo "Usage: bash collect_schema.sh DATABASE_NAME DATABASE_USERNAME" >&2
    exit 2
fi
case "$1" in
    ''|*[!A-Za-z0-9_]*) echo "Use a database name containing letters, digits or underscores only." >&2; exit 2 ;;
esac
xhibit_schema_client=$(command -v mysql || command -v mariadb || true)
if [ -z "$xhibit_schema_client" ]; then
    echo "No mysql/mariadb client installed. Nothing has been installed or changed." >&2
    exit 1
fi
xhibit_schema_dir=$(mktemp -d /tmp/xhibit-schema.XXXXXX)
xhibit_schema_output="$xhibit_schema_dir/schema-metadata.txt"
echo "Use the approved database account; its password is prompted, not placed in arguments." >&2
"$xhibit_schema_client" --no-defaults --host=localhost --user="$2" --password --database="$1" --batch --raw > "$xhibit_schema_output" <<'SQL'
SELECT VERSION() AS server_version, DATABASE() AS schema_name;
SHOW FULL TABLES;
SELECT TABLE_NAME,TABLE_TYPE,ENGINE,TABLE_COLLATION
FROM information_schema.TABLES
WHERE TABLE_SCHEMA=DATABASE()
AND LOWER(TABLE_NAME) IN ('site','cdu','urlmappings','mac_to_ip','audit','proxy_logger','cdu_logger')
ORDER BY TABLE_NAME;
SELECT TABLE_NAME,ORDINAL_POSITION,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,EXTRA,COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA=DATABASE()
AND LOWER(TABLE_NAME) IN ('site','cdu','urlmappings','mac_to_ip','audit','proxy_logger','cdu_logger')
ORDER BY TABLE_NAME,ORDINAL_POSITION;
SELECT TABLE_NAME,INDEX_NAME,NON_UNIQUE,SEQ_IN_INDEX,COLUMN_NAME,SUB_PART,INDEX_TYPE
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA=DATABASE()
AND LOWER(TABLE_NAME) IN ('site','cdu','urlmappings','mac_to_ip','audit','proxy_logger','cdu_logger')
ORDER BY TABLE_NAME,INDEX_NAME,SEQ_IN_INDEX;
SELECT TABLE_NAME,CONSTRAINT_NAME,COLUMN_NAME,REFERENCED_TABLE_NAME,REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA=DATABASE()
AND LOWER(TABLE_NAME) IN ('site','cdu','urlmappings','mac_to_ip','audit','proxy_logger','cdu_logger')
ORDER BY TABLE_NAME,CONSTRAINT_NAME,ORDINAL_POSITION;
SQL
echo "Completed metadata-only collection: $xhibit_schema_output"
echo "Review this private file before sharing. If any SQL failed, do not treat a partial file as complete."
