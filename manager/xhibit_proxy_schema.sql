DROP TABLE IF EXISTS MAC_TO_IP;
DROP TABLE IF EXISTS CDU;
DROP TABLE IF EXISTS SITE;

CREATE TABLE SITE (
	id INT NOT NULL AUTO_INCREMENT,
	title VARCHAR(30) NOT NULL,
	alert VARCHAR(500),
	xsl VARCHAR(50) NOT NULL,
	selectorUrl  VARCHAR(500) NOT NULL,
	pageUrl VARCHAR(500) NOT NULL,
	powersaveSchedule VARCHAR(2000) NOT NULL,
	PRIMARY KEY ( id )
);

insert into SITE (title, xsl) values ('Old Site #1', 'xhibit1.xsl');
insert into SITE (title, xsl) values ('New Site #2', 'xhibit2.xsl');
/*
alter table SITE add column xsl VARCHAR(50) NOT NULL;
update SITE set xsl='xhibit1.xsl';

alter table SITE add column selectorUrl VARCHAR(500) NOT NULL; 
alter table SITE add column pageUrl VARCHAR(500) NOT NULL; 
update SITE set selectorUrl = 'http://localhost/xhibit/selector.php?siteId=44' where id=2;
update SITE set pageUrl = 'http://localhost/xhibit/page.php?login=true&ignoreBrowser=true&frameWidth=0&managerReloadMinutes=30&stylesheet=&' where id=2;
update SITE set selectorUrl = 'http://localhost/xhibit/selector.php?siteId=1' where id=1;
update SITE set pageUrl = 'http://localhost/xhibit/page.php?login=true&ignoreBrowser=true&frameWidth=0&managerReloadMinutes=30&stylesheet=&' where id=1;
*/


/* The site's XSL script name can be overriden on individual CDUs*/
CREATE TABLE CDU (
	id INT NOT NULL AUTO_INCREMENT,
	macAddress VARCHAR(17) NOT NULL,
	title VARCHAR(30) NOT NULL,
	description VARCHAR(500),
	location VARCHAR(50) NOT NULL,
	url VARCHAR(255) NOT NULL,
	screenX INT NOT NULL,
	screenY INT NOT NULL,
	refresh INT NOT NULL,
	ipAddr VARCHAR(15),
	notification VARCHAR(500),
	xsl VARCHAR(50),
	fkSITE INT NOT NULL,
	FOREIGN KEY fkSITE (fkSITE) REFERENCES SITE(id) ON DELETE NO ACTION ON UPDATE NO ACTION,
	PRIMARY KEY ( id )
);
/*alter table CDU add column xsl VARCHAR(50);*/


INSERT INTO CDU (macAddress, title, description, location, url, screenX, screenY, refresh, ipAddr, fkSITE)
   VALUES ('b8:27:eb:d1:b7:44', 'Reception', 'The first court screen', 'demo1', 'http://localhost/xhibit/Snares_reception_09092015.html', 976, 736, 60, '192.168.0.17', 1);

INSERT INTO CDU (macAddress, title, description, location, url, screenX, screenY, refresh, ipAddr, fkSITE)
   VALUES ('B8:27:EB:57:41:EA', 'Court 2', 'The second court screen', 'demo2', 'http://localhost/xhibit/CCC_court1_page2_09092015.html', 800, 600, 10, '192.168.0.18', 1);

INSERT INTO CDU (macAddress, title, description, location, url, screenX, screenY, refresh, ipAddr, fkSITE)
   VALUES ('B8:27:EB:16:41:EA', 'Reception', 'The reception scrolling screen', 'reception', 'http://localhost/xhibit2/Snares_reception_09092015.html', 1776, 952, 60, '192.168.0.18', 2);
INSERT INTO CDU (macAddress, title, description, location, url, screenX, screenY, refresh, ipAddr, fkSITE)
   VALUES ('B8:27:EB:16:b7:44', 'Room 1', 'The first court screen', 'Room 1', 'http://localhost/xhibit2/CCC_court1_page2_09092015.html', 800, 600, 10, '192.168.0.17', 2);

   
CREATE TABLE MAC_TO_IP (
	id INT NOT NULL AUTO_INCREMENT,
	ipAddress VARCHAR(15) NOT NULL,
	fkCDU INT NOT NULL,
	ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	FOREIGN KEY fkCDU (fkCDU) REFERENCES CDU(id) ON DELETE NO ACTION ON UPDATE NO ACTION,
	PRIMARY KEY ( id )
);

INSERT INTO MAC_TO_IP (ipAddress, fkCDU) values ('192.168.0.17', 1);
INSERT INTO MAC_TO_IP (ipAddress, fkCDU) values ('192.168.0.177', 2);
INSERT INTO MAC_TO_IP (ipAddress, fkCDU) values ('192.168.0.18', 1);
INSERT INTO MAC_TO_IP (ipAddress, fkCDU) values ('192.168.0.178', 2);
INSERT INTO MAC_TO_IP (ipAddress, fkCDU) values ('192.168.0.167', 3);
INSERT INTO MAC_TO_IP (ipAddress, fkCDU) values ('192.168.0.157', 4);
INSERT INTO MAC_TO_IP (ipAddress, fkCDU) values ('192.168.0.168', 3);
INSERT INTO MAC_TO_IP (ipAddress, fkCDU) values ('192.168.0.158', 4);

CREATE TABLE AUDIT (
	id INT NOT NULL AUTO_INCREMENT,
	eventTimestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	username varchar(50) NOT NULL,
	eventType varchar(50) NOT NULL,
	eventData varchar(5000) NOT NULL,
	PRIMARY KEY (id)
);

CREATE TABLE CDU_LOGGER (
	id INT NOT NULL AUTO_INCREMENT,
	eventTimestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	macAddress VARCHAR(17) NOT NULL,
	pageIndex INT,
	errorCode varchar(50) NOT NULL,
	PRIMARY KEY (id)
);

CREATE TABLE PROXY_LOGGER (
	id INT NOT NULL AUTO_INCREMENT,
	eventTimestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	macAddress VARCHAR(17) NOT NULL,
	pageIndex INT,
	errorCode varchar(50) NOT NULL,
	errorMsg varchar(500) NOT NULL,
	url varchar(500),
	xhibitResponse varchar(5000),
	PRIMARY KEY (id)
);

/*
20160409
alter table SITE add column powersaveSchedule VARCHAR(2000) NOT NULL;
update SITE set powersaveSchedule = '[
	{ "priority" : 51,
	  "label" :		 "Weekends",
	  "day" :		["Saturday", "Sunday" ],
	   "schedule" : [{ "from" : "00:00", "to" : "23:59" }]
	},
    { "priority" : 50,
	 "label" :		 "Bank Holidays",
	 "date" :		["2016-03-25",
					 "2016-03-28",
					 "2016-05-02",
					 "2016-05-30",
					 "2016-08-29",
					 "2016-12-26",
					 "2016-12-27",
					 "2017-01-02",
					 "2017-04-14",
					 "2017-04-17",
					 "2017-05-01",
					 "2017-05-29",
					 "2017-08-28",
					 "2017-12-25",
					 "2017-12-26"],
	   "schedule" : [{ "from" : "00:00", "to" : "23:59" }]
	},
	{ "priority" : 52,
	  "label" :		 "Weekdays",
	  "day" :		["Monday", "Tuesday", "Wednesday", "Thursday", "Friday" ],
	   "schedule" : [{ "from" : "00:00", "to" : "08:59" }, { "from" : "14:30", "to" : "15:40" }, { "from" : "17:00", "to" : "23:59" }]
	}
]';

alter table CDU drop column screenY;
alter table CDU drop column screenX;

20160410
The Manager application on the localproxy needs to reference the CDU by either IP address (when
not using DHCP/DNS (as in testing), or by DNS name, as with the case of target deployment, so ipAddr
needs to be long enough to store a fully qualified domain name for the CDU.
alter table CDU modify column ipAddr varchar(100);

*/