<?php
/*
 * managerSiteDB-sql.php
 * 
 */
 
$this->dbSQL[UPDATE_SQL] = "UPDATE `SITE` SET
`title` = :title,
`xsl` = :xsl,
`alert` = :alert,
`selectorUrl` = :selectorUrl,
`pageUrl` = :pageUrl,
`powersaveSchedule` = :powersaveSchedule
WHERE id=:SITEid;";

$this->dbSQL[SELECT_ALL_SQL] = "SELECT `CDU`.`id` as `CDUid`, `SITE`.`id` as `SITEid`, `SITE`.`title` as `site`, `CDU`.`title` as `title` FROM `CDU`, `SITE` WHERE `SITE`.`id` = `CDU`.`fkSITE` ORDER BY SITEid, CDUid asc;";
$this->dbSQL[SELECT_SINGLE_SQL] = "SELECT `id`, `title`, `xsl`, `selectorUrl`, `pageUrl`, `alert`, `powersaveSchedule` FROM `SITE` WHERE `SITE`.`id` = :SITEid;";
 ?>