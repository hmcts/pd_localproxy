<?php
/*
 * visitorLogDB.php
 * 
 */
 
$this->dbSQL[UPDATE_SQL] = "UPDATE `CDU` SET
`macAddress` = :macAddress,
`title` = :title,
`description` = :description,
`location` = :location,
`url` = :url,
`xsl` = :xsl,
`refresh` = :refresh WHERE id=:CDUid;";

$this->dbSQL[RESET_NOTIFICATION_UPDATE_SQL] = "UPDATE `CDU` SET
`notification` = null WHERE id=:CDUid;";

$this->dbSQL[NOTIFICATION_UPDATE_SQL] = "UPDATE `CDU` SET
`notification` = :notification WHERE id=:CDUid;";

$this->dbSQL[SELECT_ALL_SQL] = "SELECT `CDU`.`id` as `CDUid`, `SITE`.`id` as `SITEid`, `SITE`.`title` as `site`, `CDU`.`title` as `title` FROM `CDU`, `SITE` WHERE `SITE`.`id` = `CDU`.`fkSITE` ORDER BY site, title asc;";
$this->dbSQL[SELECT_SINGLE_SQL] = "SELECT `CDU`.`id` as `id`, `SITE`.`title` as `site`, `CDU`.`title`, `macAddress`, `description`, `ipAddr`, `location`, `url`, `CDU`.`xsl` as `xsl`, `refresh`, `notification` FROM `CDU`, `SITE` WHERE `SITE`.`id` = `CDU`.`fkSITE` and `CDU`.id=:CDUid;";

$this->dbSQL[SELECT_IPHISTORY_SQL] = "select `ipAddress`, `ts` FROM `MAC_TO_IP` WHERE fkCDU=:CDUid ORDER BY ts desc LIMIT :maximumRows;";
$this->dbSQL[SELECT_SELECTOR_URL] = "select `selectorUrl` FROM `SITE`, `CDU` WHERE `CDU`.id=:CDUid AND `CDU`.fkSITE = `SITE`.id";

 ?>