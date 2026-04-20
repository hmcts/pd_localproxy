create database localproxy;
grant all on localproxy.* to 'localproxy'@'localhost' identified by 'localproxy';
flush privileges;
exit